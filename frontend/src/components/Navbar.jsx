import { Link } from "react-router-dom";

/**
 * Top navigation bar. `crumb` optionally shows the current context
 * (e.g. a project name) to the right of the brand.
 */
export default function Navbar({ crumb, right }) {
  return (
    <nav className="app-navbar">
      <Link to="/" className="brand">
        ForgoteLabeling
      </Link>
      {crumb ? <span className="crumb">/ {crumb}</span> : null}
      <span className="spacer" />
      {right}
    </nav>
  );
}
