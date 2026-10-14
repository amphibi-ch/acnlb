/* Node harness for tests/test_form_parity.py.
 *
 * site/item-form.js is a second implementation of scaffold.py + rubric.py, and
 * the only way to justify a second implementation is to prove it agrees. The
 * pytest suite shells out to this file, feeds both sides the same input and
 * compares. Not a browser test: jsdom is not installable here, and the logic
 * under test is deliberately DOM-free.
 *
 * Usage:  node tests/form_harness.js <op> <payload.json>
 *   build      {intake, id?}                    -> the files `acnlb new` writes
 *   rubric     {text}                           -> parsed rubric
 *   roundtrip  {row}                            -> row -> intake -> parsed
 *   zip        {entries, out}                   -> writes a store-zip, prints sha256
 */
"use strict";

var fs = require("fs");
var path = require("path");
var crypto = require("crypto");

var root = path.join(__dirname, "..");
var form = require(path.join(root, "site", "item-form.js"));
var schema = JSON.parse(fs.readFileSync(path.join(root, "site", "schema.json"), "utf8"));

var op = process.argv[2];
var payload = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
var result;

if (op === "build") {
  var intake = form.parseIntake(payload.intake, schema);
  var built = form.buildItem(intake, { id: payload.id || null, schema: schema });
  result = built.ok
    ? {
        ok: true, id: built.id, warnings: built.warnings,
        lint: form.lintItem(built, schema),
        files: form.assembleFiles(built),
        item: built.item
      }
    : { ok: false, errors: built.errors };
} else if (op === "rubric") {
  result = form.parseRubric(payload.text);
} else if (op === "roundtrip") {
  var text = form.rowToIntake(payload.row);
  var re = form.parseIntake(text, schema);
  result = { text: text, rebuilt: form.intakeToRow(re), errors: re.errors };
} else if (op === "zip") {
  var bytes = form.makeZip(payload.entries);
  fs.writeFileSync(payload.out, Buffer.from(bytes));
  result = {
    path: payload.out,
    bytes: bytes.length,
    sha256: crypto.createHash("sha256").update(Buffer.from(bytes)).digest("hex")
  };
} else {
  console.error("unknown op: " + op);
  process.exit(2);
}

process.stdout.write(JSON.stringify(result));
