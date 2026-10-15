/** A colour next to its name: in the legend, the list and the detail. Identity is never colour alone. */
export default function Swatch({ color }: { color: string }) {
  return <span className="area-swatch" style={{ background: color }} />;
}
