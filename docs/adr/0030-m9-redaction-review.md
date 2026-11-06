# 0030 — M9 redaction review: scan before writing, listed content and a stricter scanner
- **Status:** Accepted (2026-11-06). Refines [0029](0029-m9-snapshot-export.md), and replaces its decision 7's rule table and the order of writing and scanning. The rest of 0029 stays in force. M9 stays open until the live snapshot is reviewed and committed, which comes after M8 closes.

## Context
The redaction review read `core/verity_core/export/` and `tests/export/`, and attacked them with experiments. It made no AWS call of any kind, so every result comes from the fixture and hand-built graphs.

**What held.** Account redaction worked in all 26 tests: a digest planted in a node ID, tag key or value, env name, signal, Risk description, Candidate signal, `job_title`, run summary key, run version, ChangeEvent ID, or Evidence content or key was replaced each time. No prefix of any old hash survived, down to 8 hex digits, in any case. All 107 Evidence references resolved. Rebuilt hashes cover only published text, so they cannot be used to test candidate digests. Output was byte-identical across hash seeds and time zones. The stale check refused every tampered graph and accepted honest histories. The contract regenerates identically on Node 26, though CI uses Node 24, and an untracked generated file is caught.

**What failed.**
| # | Finding | Experiment |
|---|---|---|
| 1 | The scan ran after the file was written, so a crash left an unscanned file in the target folder. Git did not ignore its name | `os._exit` inside the scan and before the rename: both left `.snapshot-*.tmp` |
| 2 | Free-form values bypassed the listed fields. Decision 3 listed model fields, but not Evidence content keys or tags | A tag `owner: <a person's name>` and an unknown content key were both published, with no scan hit |
| 3 | The scanner missed real forms | 32 of 59 hostile strings that should have been caught were not (below) |
| 4 | A published hash could be false | Content naming a rebuilt Evidence ID was edited after hashing: the hash stopped matching, even with `redacted: false` |
| 5 | A foreign role could be labelled as the owner's | A foreign role sorted first became `000000000000`, and the owner became `acct_1`. No digest leaked, but the file would have said something false |
| 6 | Evidence with a `content_ref` and a digest in its subject was refused by its own scan | It kept its file hash and also listed it as replaced |
| 7 | Demo data could look real | The header left out synthetic records. Findings had no `simulated` flag. On the fixture, "simulated sign-offs" fired for any simulated Evidence |
| 8 | Nothing enforced the 2 MB limit, the file was written `0600`, and the schema marked always-written fields as optional | Read and measured |
| 9 | `--check` passed a fixture and any extra field, and CI checked one path only | Run by hand |
| 10 | The suite missed 19 of 58 mutants | Each was applied in a throwaway worktree |

The scanner's misses included an account next to another digit, `ev:<account>`, a 64-hex value anywhere, uppercase digests and Function URLs, percent-encoded URLs and emails, `a@example.com-x`, `assumed-role` ARNs and repeated JSON keys. Its "exactly 12 digits" also fell short of decision 7's "any run of 12 digits".

## Decision
1. **Scan first.** `write_snapshot` scans the serialised text in memory, and only then touches the disk. Unscanned text can no longer reach a file, crash or not. The temporary file is flushed, set to `0644` and renamed. `.snapshot-*.tmp` is ignored by git.
2. **Evidence content keys are listed, and an unlisted key refuses the export.** The lists cover the top level by kind, `config`, policies, statements and trust. The shape is Verity's own, so a new key is a decision. The fixture runs real crawler configs through this, so a new crawler key fails a test before any live export.
3. **Tags are listed, and an unlisted tag is left out.** The list is `ai:system-id`, `project` and `verity:component`. Tags are set outside Verity, so an unknown tag is expected, and it is dropped from the resource and its Evidence. Dropping it changes the content, so the Evidence is rebuilt. The header counts what was left out. No pattern can recognise a person's name, so this is the control for names.
4. **The scanner's rules are replaced.**

   | Category | Rule |
   |---|---|
   | Account ID | A run of 12 or more digits, except `000000000000`, or three groups of 4 split by a dash or space. Whole numbers count, fractions do not |
   | Digit exemption | Only a value that is exactly a hash: 64 hex under `sha256` or `file_sha256`, or the exact shape of an Evidence or ChangeEvent ID |
   | Digest | `acct`, an optional `_` or `-`, and 8 hex digits, in any case |
   | Function URL | `lambda-url.`, `.on.aws` or `execute-api.`, in any case |
   | Email | `@`, a dotted domain and at least one letter in it, so `crawler@0.1.0` passes |
   | Canary | As before, in any case |
   | Identity and paths | `user`, `assumed-role` or `federated-user` ARNs, and `/Users/`, `/home/`, `/root/`, `/private/`, `/var/folders/`, `C:\Users\` |
   | AWS key IDs | `AKIA`, `ASIA`, `AROA`, `AIDA`, `ANPA` or `ANVA` and 16 characters (new) |
   | Old hashes | Any replaced or withheld hash, whole or as a run of 12 hex digits, in any case |

   Every rule reads the text as it stands, percent-decoded up to three times, and Unicode-normalised. Repeated JSON keys and `NaN` are invalid. `crawler@` versions with letters, such as `1.2.3-rc1`, would be refused, which is the safe way to fail.
5. **Config hashes are handed to the scanner.** They are withheld, and no route to publication was found, but the scanner now refuses them too.
6. **Every published hash is checked.** Redaction recomputes the hash of all inline Evidence at the end, and refuses on a mismatch. Content naming a rebuilt ID is therefore refused, not repaired. Nothing does this today.
7. **Two accounts in function roles refuse the export.** A function's role is always in its own account, so two digests mean the graph is wrong. A live export with no owner's account is refused as well.
8. **The file says what is not real.** The header lists simulated providers, simulated sign-offs (only sign-off Evidence), and counts of synthetic and simulated records. A finding about one control result carries `control_id` and `simulated`.
9. **The rest:** export refuses a file over 2 MiB. The schema is generated in serialisation mode, so every written field is required. `--check` validates against the snapshot models. `--require-live` refuses a fixture, and CI uses it on every `web/public/data/*.json`.

## For PR C
- **`--as-of` with a date means the start of that day,** but `verity assess` treats today as now. A live export must use now, or the stale check will refuse a good graph.
- **The commit SHA is 40 hex digits,** so the field needs its own exact-shape exemption from the digit rule.
- **Decision 7 of 0029 has no live test yet.** Run the scan on the first live file before anything else.

## Alternatives
| Option | Why not chosen |
|---|---|
| Keep the temporary file outside the publish folder | Rename would no longer be atomic, and scanning first removes the problem |
| Refuse an unlisted tag | One stray tag in the account would block every export |
| Drop an unlisted content key silently | A new crawler field would vanish with no decision made |
| Scan for people's names | Not possible by pattern. Listing is the control |
| Repair content that names a rebuilt ID | Needs ordering across Evidence for a case that does not exist. Refusing is simpler and safe |
| Treat `simulated` as a new `source` on derived rows | One `source` to one badge stands (D12). A separate flag keeps both facts |

## Consequences
- A digit run of 12 or more in any ordinary field now refuses the export, even if it is harmless. The fixture has none, including with microsecond timestamps.
- The size check is on the file before compression. The fixture is 1.23 MiB, and gzip takes it to about 52 KB. Live should be about 1.3 MiB, and by April 2027 about 1.5 MiB, estimated from the daily crawl's growth.
- `Finding` gains an optional `control_id`, which is ignored outside the export.
- **Mutation result after the fixes:** of 99 mutants of the redaction, scanner, build, derived rows and `--check`, 2 survive. Both remove a defensive check that cannot fire today (`no lost refs`, `no old id`), and both stay. This was a hand-picked list, so it shows the suite is better, not that it is complete.
- **Not proved:** that nothing sensitive exists beyond the listed fields and rules, and any behaviour on the live graph. `Requirement` summaries, decision statements, names and `purpose` are free text from reviewed YAML, and only the scan checks them. A hash split across two keys would not be found.
