const net = require("net");

const LISTEN_PORT = parseInt(process.env.LISTEN_PORT || "8443", 10);
const TARGET_HOST = process.env.TARGET_HOST || "10.4.99.35";
const TARGET_PORT = parseInt(process.env.TARGET_PORT || "8443", 10);

const server = net.createServer((client) => {
  client.pause();

  const target = net.connect(TARGET_PORT, TARGET_HOST, () => {
    client.pipe(target);
    target.pipe(client);
    client.resume();
  });

  client.on("error", (e) => {
    target.destroy();
  });
  target.on("error", (e) => {
    client.destroy();
  });
});

server.listen(LISTEN_PORT, "0.0.0.0", () => {
  console.log(`[relay] 0.0.0.0:${LISTEN_PORT} -> ${TARGET_HOST}:${TARGET_PORT}`);
});
