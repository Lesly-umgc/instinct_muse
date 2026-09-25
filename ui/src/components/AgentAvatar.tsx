export default function AgentAvatar({ size = 56 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden="true">
      <circle cx="32" cy="32" r="30" fill="#efe9df" />
      <circle cx="24" cy="28" r="3" fill="#4a4238" />
      <circle cx="40" cy="28" r="3" fill="#4a4238" />
      <path d="M24 39 q8 7 16 0" stroke="#4a4238" strokeWidth="2.5" fill="none" strokeLinecap="round" />
      <circle cx="18" cy="35" r="3.4" fill="#f5c9b8" opacity="0.8" />
      <circle cx="46" cy="35" r="3.4" fill="#f5c9b8" opacity="0.8" />
    </svg>
  );
}
