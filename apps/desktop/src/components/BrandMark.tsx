import mark from "../assets/pex-mark.svg";

export function BrandMark({ label = false }: { label?: boolean }) {
  return (
    <span
      className="brand-lockup"
      aria-label={label ? "PEX" : undefined}
      aria-hidden={label ? undefined : true}
    >
      <img className="brand-mark" src={mark} alt="" />
      {label ? <span className="brand-wordmark">PEX</span> : null}
    </span>
  );
}
