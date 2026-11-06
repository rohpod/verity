// A static server for the production build, with no dependency. Serves web/.prod, so the app is
// at /verity/ the way a project page on GitHub Pages would be. It sets no CSP header: the page's
// own meta tag is the policy under test.
import { createServer } from "node:http";
import { readFile, stat } from "node:fs/promises";
import path from "node:path";

const root = path.resolve(import.meta.dirname, "..", ".prod");
const port = Number(process.argv[2] ?? 4174);
const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml" };

createServer(async (request, response) => {
  const url = new URL(request.url ?? "/", "http://localhost");
  let file = path.join(root, decodeURIComponent(url.pathname));
  if (!file.startsWith(root)) {
    response.statusCode = 403;
    return response.end();
  }
  try {
    if ((await stat(file)).isDirectory()) file = path.join(file, "index.html");
    const body = await readFile(file);
    response.setHeader("Content-Type", types[path.extname(file)] ?? "application/octet-stream");
    response.end(body);
  } catch {
    response.statusCode = 404;
    response.end("not found");
  }
}).listen(port, () => console.log(`serving ${root} on ${port}`));
