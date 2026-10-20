// Entry point Node.js App cPanel/Passenger.
// Jalankan `npm run build` lebih dulu, lalu startup file ini.
/* eslint-disable @typescript-eslint/no-require-imports */
const { createServer } = require("node:http");
const next = require("next");

process.env.NODE_ENV = process.env.NODE_ENV || "production";

const app = next({ dev: false, dir: __dirname });
const handle = app.getRequestHandler();
const port = process.env.PORT || 3000;

app
  .prepare()
  .then(() => {
    createServer((request, response) => handle(request, response)).listen(
      port,
      () => {
        console.log(`Pointse berjalan di ${port}`);
      },
    );
  })
  .catch((error) => {
    console.error("Gagal menjalankan Pointse:", error);
    process.exit(1);
  });
