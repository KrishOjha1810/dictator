import type { ReactNode } from "react";
import Nav from "./Nav";
import "./PageHeader.css";

export default function PageHeader({
  eyebrow,
  title,
  intro,
  children,
}: {
  eyebrow: string;
  title: string;
  intro: string;
  children?: ReactNode;
}) {
  return (
    <section className="c-pagehead frame">
      <div className="head">
        <div className="backdrop" aria-hidden="true"></div>
        <div className="inner">
          <Nav />
          <div className="copy">
            <span className="eyebrow">{eyebrow}</span>
            <h1>{title}</h1>
            <p>{intro}</p>
            {children}
          </div>
        </div>
      </div>
    </section>
  );
}
