/**
 * The fields of a curation patch entry, read off the patch contract
 * (names/curate-patch.schema.json). Said once, here, for the dev server that
 * stores entries (curate.ts) and for the test that pins the browser's
 * hand-written `PatchEntry` to the contract (src/dev/curate/patch.test.ts) —
 * which is why this module imports nothing but the schema: it is compiled for
 * Node and for the browser.
 */
import patchSchema from '../../names/curate-patch.schema.json' with { type: 'json' };

/** The fields an action's branch of `allOf` adds; `clear` has none of its own. */
const branchFields = patchSchema.allOf.flatMap((branch) =>
  Object.keys(branch.then.properties ?? {}),
);

/**
 * Every field the schema defines: those of every entry (its `properties`) and
 * those of each action (its branch's `then.properties`), each named once.
 */
export const PATCH_FIELDS: readonly string[] = [
  ...new Set([...Object.keys(patchSchema.properties), ...branchFields]),
];
