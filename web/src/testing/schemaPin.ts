// Test support: pins a hand-written TypeScript type to the JSON Schema of the
// file it describes (names/*.schema.json), so that a field changed on one side
// only — renamed, added, dropped, made optional, of another JSON type — fails
// a test.
//
//   const pin: Pin<CurateCandidate> = { ref: { string: true }, km: { number: true, null: true }, … };
//   expect(pinnedFields(pin)).toEqual(schemaFields(schema.$defs.candidate, schema));
//
// The pin is written by hand and compiles only while it says what the type
// says; the comparison fails when the schema says something else.

/** The JSON types of a TypeScript type, as a schema's `type` names them. */
type JsonType<T> = T extends string
  ? 'string'
  : T extends number
    ? 'number'
    : T extends boolean
      ? 'boolean'
      : T extends null
        ? 'null'
        : T extends readonly unknown[]
          ? 'array'
          : 'object';

/** `optional` for a field that may be left out. */
type Optional<T> = undefined extends T ? 'optional' : never;

/** What a pin says of each field of `T`: its JSON types, and `optional` where it may be left out. */
export type Pin<T> = {
  [K in keyof T]-?: Record<JsonType<Exclude<T[K], undefined>> | Optional<T[K]>, true>;
};

/** A node of a JSON Schema, as far as a pin reads one. */
export interface SchemaNode {
  type?: string | string[];
  enum?: unknown[];
  const?: unknown;
  $ref?: string;
  properties?: Record<string, SchemaNode>;
  required?: string[];
  $defs?: Record<string, SchemaNode>;
}

/** What a pin or a schema says of the fields of an object: per field, sorted. */
export type Fields = Record<string, string[]>;

export function pinnedFields<T>(pin: Pin<T>): Fields {
  const fields: Fields = {};
  for (const [name, said] of Object.entries(pin)) fields[name] = Object.keys(said as object).sort();
  return fields;
}

/** The fields of the object `node` describes; `root` is the schema it is in, for its `$ref`s. */
export function schemaFields(node: SchemaNode, root: SchemaNode = node): Fields {
  const required = new Set(node.required);
  const fields: Fields = {};
  for (const [name, property] of Object.entries(node.properties ?? {})) {
    const said = new Set(jsonTypes(resolve(property, root)));
    if (!required.has(name)) said.add('optional');
    fields[name] = [...said].sort();
  }
  return fields;
}

/** The node a `$ref` into the schema's own `$defs` names, or the node itself. */
function resolve(node: SchemaNode, root: SchemaNode): SchemaNode {
  const name = node.$ref?.replace('#/$defs/', '');
  return name === undefined ? node : (root.$defs?.[name] ?? {});
}

function jsonTypes(node: SchemaNode): string[] {
  const values = node.enum ?? ('const' in node ? [node.const] : undefined);
  if (values) return values.map((value) => (value === null ? 'null' : typeof value));
  // TypeScript has one number type.
  return [node.type ?? []].flat().map((type) => (type === 'integer' ? 'number' : type));
}
