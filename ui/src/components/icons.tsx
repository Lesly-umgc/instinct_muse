const S = ({ d }: { d: string }) => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d={d} />
  </svg>
);

export const ChatIcon = () => <S d="M21 12a8 8 0 0 1-8 8H4l2-3a8 8 0 1 1 15-5z" />;
export const FeedIcon = () => <S d="M4 5h13v14H6a2 2 0 0 1-2-2V5zm13 3h3v9a2 2 0 0 1-2 2h-1M7 9h6M7 13h6" />;
export const IdeasIcon = () => <S d="M9 18h6M10 21h4M12 3a6 6 0 0 0-4 10c.8.8 1 1.6 1 3h6c0-1.4.2-2.2 1-3a6 6 0 0 0-4-10z" />;
export const GoalsIcon = () => <S d="M12 21a9 9 0 1 1 0-18 9 9 0 0 1 0 18zm0-5a4 4 0 1 1 0-8 4 4 0 0 1 0 8zm0-3a1 1 0 1 1 0-2 1 1 0 0 1 0 2z" />;
export const LibraryIcon = () => <S d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" />;
