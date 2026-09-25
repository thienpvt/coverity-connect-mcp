#!/usr/bin/env python3
"""
Coverity Connect API Client
Provides async interface for interacting with Coverity Connect (Black Duck) REST API
"""

import aiohttp
import asyncio
import json
import logging
import os
from typing import List, Dict, Any, Optional
from urllib.parse import quote, unquote, urljoin, urlsplit
import ssl

logger = logging.getLogger(__name__)

class CoverityClient:
    """Async client for Coverity Connect REST API"""
    
    def __init__(self, host: str, port: int = 8080, use_ssl: bool = True, 
                 username: Optional[str] = None, password: Optional[str] = None):
        """
        Initialize Coverity Connect client
        
        Args:
            host: Coverity Connect server hostname
            port: Server port (default: 8080)
            use_ssl: Use HTTPS connection (default: True)
            username: Authentication username (if None, will use COVAUTHUSER env var)
            password: Authentication password/token (if None, will use COVAUTHKEY env var)
            
        Raises:
            ValueError: When authentication credentials are not provided
        """
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
        
        # セキュアな認証情報の処理
        self.username = username or os.getenv('COVAUTHUSER')
        self.password = password or os.getenv('COVAUTHKEY')  # nosec B105
        
        # テスト環境での特別処理
        if os.getenv('TESTING') == 'true':
            logger.warning("TESTING mode enabled - using test credentials if not provided")
            if not self.username:
                self.username = "test_user"
            if not self.password:
                self.password = "test_key"  # nosec B105
        else:
            # 本番環境では必須チェック
            if not self.username:
                raise ValueError("Username is required. Provide via parameter or COVAUTHUSER env var.")
            
            if not self.password:
                raise ValueError("Password is required. Provide via parameter or COVAUTHKEY env var.")
        
        # Build base URL
        protocol = "https" if use_ssl else "http"
        self.base_url = f"{protocol}://{host}:{port}"
        
        # Session will be created when needed
        self._session: Optional[aiohttp.ClientSession] = None
        
        logger.info(f"Initialized Coverity client for {self.base_url} (user: {self.username})")
    
    @classmethod
    def from_env(cls, host: str, port: int = 8080, use_ssl: bool = True):
        """
        環境変数から認証情報を読み込んでクライアントを作成
        
        Args:
            host: Coverity Connect server hostname
            port: Server port (default: 8080)
            use_ssl: Use HTTPS connection (default: True)
            
        Returns:
            CoverityClient: 初期化されたクライアント
        """
        return cls(host=host, port=port, use_ssl=use_ssl)
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session"""
        if self._session is None or self._session.closed:
            # Create SSL context
            ssl_context = None
            if self.use_ssl:
                ssl_context = ssl.create_default_context()
                # For testing with self-signed certificates
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
            
            # Create auth header
            auth = aiohttp.BasicAuth(self.username, self.password)
            
            # Create session with timeout (fetching all projects/defects can take ~60s)
            timeout = aiohttp.ClientTimeout(total=180, connect=30, sock_read=120)
            
            # Configure proxy if available
            proxy = None
            proxy_auth = None
            
            # Check for proxy settings from environment
            http_proxy = os.getenv('HTTP_PROXY') or os.getenv('http_proxy')
            https_proxy = os.getenv('HTTPS_PROXY') or os.getenv('https_proxy')
            
            if self.use_ssl and https_proxy:
                proxy = https_proxy
                logger.info(f"Using HTTPS proxy: {proxy}")
            elif not self.use_ssl and http_proxy:
                proxy = http_proxy
                logger.info(f"Using HTTP proxy: {proxy}")
            
            connector = aiohttp.TCPConnector(ssl=ssl_context) if ssl_context else None
            
            self._session = aiohttp.ClientSession(
                auth=auth,
                timeout=timeout,
                connector=connector,
                headers={
                    'Accept': 'application/json',
                    'Content-Type': 'application/json'
                }
            )
        
        return self._session
    
    async def close(self):
        """Close HTTP session"""
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def _make_request(self, method: str, endpoint: str, 
                           params: Dict[str, Any] = None, 
                           data: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Make HTTP request to Coverity Connect API
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            params: Query parameters
            data: Request body data
            
        Returns:
            JSON response data
        """
        session = await self._get_session()
        url = urljoin(self.base_url, endpoint)
        
        try:
            logger.debug(f"Making {method} request to {url}")
            
            kwargs = {}
            if params:
                kwargs['params'] = params
            if data:
                kwargs['json'] = data
            
            # Configure proxy for this request
            http_proxy = os.getenv('HTTP_PROXY') or os.getenv('http_proxy')
            https_proxy = os.getenv('HTTPS_PROXY') or os.getenv('https_proxy')
            
            if self.use_ssl and https_proxy:
                kwargs['proxy'] = https_proxy
                logger.debug(f"Using HTTPS proxy: {https_proxy}")
            elif not self.use_ssl and http_proxy:
                kwargs['proxy'] = http_proxy
                logger.debug(f"Using HTTP proxy: {http_proxy}")
            
            async with session.request(method, url, **kwargs) as response:
                logger.debug(f"Response status: {response.status}")
                
                if response.status == 200:
                    try:
                        return await response.json()
                    except json.JSONDecodeError:
                        # Return text response if not JSON
                        text = await response.text()
                        return {"response": text}
                elif response.status == 401:
                    raise Exception("Authentication failed - check credentials")
                elif response.status == 404:
                    logger.warning(f"Resource not found: {url}")
                    return {}
                else:
                    text = await response.text()
                    raise Exception(f"HTTP {response.status}: {text}")
                    
        except aiohttp.ClientError as e:
            logger.error(f"Request failed: {e}")
            raise Exception(f"Connection error: {e}")
    
    async def get_projects(self) -> List[Dict[str, Any]]:
        """
        Get list of projects

        Returns:
            List of project dictionaries
        """
        response = await self._make_request('GET', '/api/v2/projects')

        if isinstance(response, dict):
            if 'projects' in response:
                return response['projects']
            elif 'viewContentsV1' in response:
                return response['viewContentsV1'].get('projects', [])

        return []
    
    async def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        """
        Get specific project details

        Args:
            project_id: Project identifier (name or projectKey)

        Returns:
            Project dictionary or None if not found
        """
        try:
            projects = await self.get_projects()
            pid_str = str(project_id).strip()
            for project in projects:
                if (str(project.get('projectKey')) == pid_str or
                    project.get('name') == pid_str or
                    project.get('projectName') == pid_str):
                    return project

            return None

        except Exception as e:
            logger.error(f"Failed to get project {project_id}: {e}")
            return None
    
    async def get_streams(self, project_id: str = "") -> List[Dict[str, Any]]:
        """
        Get list of streams, optionally filtered by project

        Args:
            project_id: Optional project ID to filter by

        Returns:
            List of stream dictionaries
        """
        endpoint = '/api/v2/streams'
        params = {}
        if project_id:
            params['projectId'] = project_id

        response = await self._make_request('GET', endpoint, params=params)

        if isinstance(response, dict):
            if 'streams' in response:
                return response['streams']
            elif 'viewContentsV1' in response:
                return response['viewContentsV1'].get('streams', [])

        return []
    
    async def get_defects(self, stream_id: str = "", query: str = "",
                         filters: Dict[str, str] = None,
                         limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get defects from Coverity Connect

        Args:
            stream_id: Stream identifier to filter by
            query: Search query
            filters: Additional filters (checker, severity, status, etc.)
            limit: Maximum number of results

        Returns:
            List of defect dictionaries
        """
        body = {'filters': [], 'query': query, 'rowCount': limit, 'offset': 0}
        if stream_id:
            body['filters'].append({
                'columnKey': 'stream', 'matchMode': 'oneOrMoreMatch',
                'matchers': [{'class': 'Stream', 'name': stream_id, 'type': 'nameMatcher'}]
            })
        for name, value in (filters or {}).items():
            column = {'checker': 'checker', 'severity': 'displayImpact',
                      'status': 'displayStatus', 'streamId': 'stream'}.get(name, name)
            matcher = ({'class': 'Stream', 'name': value, 'type': 'nameMatcher'}
                       if column == 'stream' else {'key': value, 'type': 'keyMatcher'})
            body['filters'].append({
                'columnKey': column, 'matchMode': 'oneOrMoreMatch', 'matchers': [matcher]
            })

        response = await self._make_request('POST', '/api/v2/issues/search', data=body)
        if isinstance(response, dict):
            if 'rows' in response:
                return [{cell['key']: cell.get('value') for cell in row} if isinstance(row, list)
                        else row for row in response['rows']]
            if 'issues' in response:
                return response['issues']
            elif 'viewContentsV1' in response:
                return response['viewContentsV1'].get('issues', [])

        return []

    async def get_view_contents(self, view_id: str, project_id: str,
                                row_count: int = 100, offset: int = 0) -> Dict[str, Any]:
        """Get one page of a project's view, preserving rows and pagination metadata."""
        if not 1 <= row_count <= 1000 or offset < 0:
            raise ValueError('row_count must be 1..1000 and offset must be nonnegative')
        return await self._make_request(
            'GET', f'/api/v2/views/viewContents/{quote(str(view_id), safe="")}',
            params={'projectId': project_id, 'rowCount': row_count, 'offset': offset}
        )

    async def get_defect_occurrences(self, cid: str) -> Any:
        """Get event trace for a Coverity issue."""
        return await self._make_request('GET', f'/api/v2/issues/{quote(str(cid), safe="")}/occurrences')

    async def coverity_api_get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Read a Coverity API path on the configured server."""
        parsed = urlsplit(path)
        segments = unquote(parsed.path).split('/')
        if (not path.startswith('/api/') or parsed.scheme or parsed.netloc or
                '?' in path or '#' in path or '\\' in path or
                any(segment in ('.', '..', '') for segment in segments[2:])):
            raise ValueError('path must be a safe /api/ path without query or fragment')
        return await self._make_request('GET', path, params=params)
    
    async def get_defect_details(self, cid: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a specific defect

        Args:
            cid: Coverity Issue Identifier

        Returns:
            Detailed defect information or None if not found
        """
        endpoint = f'/api/viewContents/issues/v1/{cid}'
        response = await self._make_request('GET', endpoint)
        return response if response else None
    
    async def get_users(self, disabled: bool = False, include_details: bool = True, 
                       locked: bool = False, limit: int = 200) -> List[Dict[str, Any]]:
        """
        Get all users from Coverity Connect
        
        Args:
            disabled: Include disabled users (default: False)
            include_details: Include detailed user information (default: True)
            locked: Include locked users (default: False)
            limit: Maximum number of users to return (default: 200)
            
        Returns:
            List of user dictionaries
        """
        params = {
            'disabled': str(disabled).lower(),
            'includeDetails': str(include_details).lower(),
            'locked': str(locked).lower(),
            'offset': '0',
            'rowCount': str(limit),
            'sortColumn': 'name',
            'sortOrder': 'asc'
        }

        response = await self._make_request('GET', '/api/v2/users', params=params)

        if response and 'users' in response:
            return response['users']

        return []
    
    async def get_user_details(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a specific user
        
        Args:
            username: Username to lookup
            
        Returns:
            User details dictionary or None if not found
        """
        try:
            response = await self._make_request('GET', f'/api/v2/users/{username}')
            
            if response and 'users' in response and response['users']:
                return response['users'][0]
            
            # Try to find user in all users list
            users = await self.get_users()
            for user in users:
                if user.get('name') == username:
                    return user
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get user details for {username}: {e}")
            return None

    async def __aenter__(self):
        """Async context manager entry"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()

# テスト専用関数（本番コードとは分離）
def create_test_client() -> CoverityClient:
    """
    テスト専用のクライアント作成関数
    本番環境では使用禁止
    """
    if os.getenv('TESTING') != 'true':
        raise RuntimeError("Test client can only be used in test environment")
    
    # テスト環境でのみ許可される  # nosec B106
    return CoverityClient(
        host="localhost",
        port=5000,
        use_ssl=False,
        username="test_user",
        password="test_key_for_testing_only"  # nosec B106
    )

# Utility functions for testing
async def test_client():
    """Test the Coverity client with secure credentials"""
    # テスト環境の設定
    os.environ['TESTING'] = 'true'
    
    try:
        # 環境変数から作成（推奨方法）
        client = CoverityClient.from_env(
            host="localhost",
            port=5000,
            use_ssl=False
        )
        
        print("Testing Coverity client...")
        
        # Test projects
        projects = await client.get_projects()
        print(f"Found {len(projects)} projects")
        
        # Test streams
        streams = await client.get_streams()
        print(f"Found {len(streams)} streams")
        
        # Test defects
        defects = await client.get_defects(limit=5)
        print(f"Found {len(defects)} defects")
        
        print("Client test completed successfully!")
        
    except Exception as e:
        print(f"Client test failed: {e}")
    finally:
        await client.close()

if __name__ == "__main__":
    # Run test
    asyncio.run(test_client())
