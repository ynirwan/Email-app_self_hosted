import React from 'react';

export default function ZeniPostLogo({ size = 32, variant = 'animated' }) {
  // Scale all dimensions based on size prop
  const scale = size / 32;
  const fontSize = size * 0.75;
  const subTextSize = size * 0.22;

  return (
    <div className="flex items-center gap-3 select-none font-sans group">
      <style>{`
        @keyframes neon-pulse {
          0%, 100% {
            filter: drop-shadow(0 0 4px rgba(34,211,238,0.4));
          }
          50% {
            filter: drop-shadow(0 0 12px rgba(59,130,246,0.7));
          }
        }
        @keyframes stream-flow {
          0% { stroke-dashoffset: 120; }
          100% { stroke-dashoffset: 0; }
        }
      `}</style>

      {/* Icon */}
      <div className="relative shrink-0" style={{ width: size, height: size }}>
        <svg
          viewBox="0 0 100 100"
          width={size}
          height={size}
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          style={
            variant === 'animated'
              ? { animation: 'neon-pulse 3s ease-in-out infinite' }
              : {}
          }
        >
          <defs>
            <linearGradient id="neonStream" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#22D3EE" />
              <stop offset="50%" stopColor="#3B82F6" />
              <stop offset="100%" stopColor="#818CF8" />
            </linearGradient>
          </defs>

          {/* Background envelope */}
          <rect
            x="15"
            y="25"
            width="70"
            height="50"
            rx="10"
            fill="url(#neonStream)"
            opacity="0.12"
          />

          {/* Stream + envelope line */}
          <path
            d="M15 25 L50 55 L85 25 M15 25 V75 H85 V25"
            stroke="url(#neonStream)"
            strokeWidth="6"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeDasharray="120"
            style={
              variant === 'animated'
                ? { animation: 'stream-flow 2.5s linear infinite' }
                : {}
            }
          />

          {/* Notification dot */}
          {variant === 'animated' && (
            <circle
              cx="85"
              cy="25"
              r="4"
              fill="#F472B6"
              stroke="#0F172A"
              strokeWidth="2"
            />
          )}
        </svg>
      </div>

      {/* Text */}
      <div className="flex flex-col justify-center overflow-hidden">
        <h1
          className="font-bold tracking-tight leading-none text-white whitespace-nowrap"
          style={{ fontSize }}
        >
          Ganga
          <span className="ml-0.5 font-light text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-indigo-400">
            Inbox
          </span>
        </h1>

        <p
          className="font-medium uppercase tracking-[0.3em] text-slate-500 whitespace-nowrap"
          style={{ fontSize: subTextSize, marginTop: 1 }}
        >
          Marketing
        </p>
      </div>
    </div>
  );
}
