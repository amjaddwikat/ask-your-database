const ThinkingIndicator = () => (
  <div className="flex items-start gap-3 px-6 py-3">
    <div className="flex items-center gap-1.5 rounded-2xl rounded-tl-sm bg-assistant-bubble px-4 py-3">
      <span className="h-2 w-2 animate-bounce rounded-full bg-primary [animation-delay:0ms]" />
      <span className="h-2 w-2 animate-bounce rounded-full bg-primary [animation-delay:150ms]" />
      <span className="h-2 w-2 animate-bounce rounded-full bg-primary [animation-delay:300ms]" />
    </div>
  </div>
);

export default ThinkingIndicator;
