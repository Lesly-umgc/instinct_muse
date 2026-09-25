export default function PlaceholderScreen({ title, body }: { title: string; body: string }) {
  return (
    <div className="main">
      <div className="placeholder">
        <div className="card">
          <h2>{title}</h2>
          <p>{body}</p>
        </div>
      </div>
    </div>
  );
}
