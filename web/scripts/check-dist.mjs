// A build must carry no snapshot and no fixture (ADR 0031, decision 3). The Pages workflow
// copies the committed snapshot in afterwards, and checks that exact file before deploying.
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";

const dist = path.resolve(process.argv[2] ?? "dist");
const problems = [];
if (existsSync(path.join(dist, "data"))) problems.push("dist/data exists");

function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name);
    return statSync(full).isDirectory() ? walk(full) : [full];
  });
}
for (const file of walk(dist)) {
  if (/snapshot\.json$/.test(file)) problems.push(`${path.relative(dist, file)} is a snapshot`);
  if (/\.(js|css|html|json)$/.test(file)) {
    const body = readFileSync(file, "utf-8");
    if (body.includes('"data_source"') || body.includes("Recorded fixture records")) {
      problems.push(`${path.relative(dist, file)} embeds snapshot content`);
    }
  }
}
if (problems.length) {
  console.error(problems.join("\n"));
  process.exit(1);
}
console.log("dist holds no snapshot or fixture.");
