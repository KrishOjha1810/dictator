import PageHeader from "../components/PageHeader";

export default function NotFound() {
  return (
    <PageHeader eyebrow="404" title="Nothing here" intro="The page you asked for doesn't exist. The download is still one click away.">
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 10 }}>
        <a className="btn btn-dark" href="/download">
          Download
        </a>
        <a className="btn btn-glass" href="/">
          Home
        </a>
      </div>
    </PageHeader>
  );
}
