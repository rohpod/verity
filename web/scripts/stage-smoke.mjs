// Stages the production build for the smoke test: the real build under a /verity/ subpath, plus
// the generated fixture copied into .prod/verity/data/. That is outside web/public/data (the
// publish path) and outside the repository's tracked files. Never run in CI's publish job.
import { cpSync, existsSync, mkdirSync } from "node:fs";
import path from "node:path";

const web = path.resolve(import.meta.dirname, "..");
const fixture = path.join(web, ".fixture", "snapshot.json");
const target = path.join(web, ".prod", "verity");
if (!existsSync(fixture)) {
  console.error("web/.fixture/snapshot.json is missing: run `npm run fixture` first.");
  process.exit(1);
}
if (!existsSync(path.join(target, "index.html"))) {
  console.error("The production build is missing: run `npm run smoke:build` first.");
  process.exit(1);
}
mkdirSync(path.join(target, "data"), { recursive: true });
cpSync(fixture, path.join(target, "data", "snapshot.json"));
console.log("staged the fixture in .prod/verity/data/ (outside web/public/data)");
