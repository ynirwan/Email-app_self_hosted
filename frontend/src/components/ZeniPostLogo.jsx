import React from 'react';

export default function ZeniPostLogo({ size = 80, variant = 'animated' }) {
  // Scale all dimensions based on size prop
  const scale = size / 80;
  const dimensions = {
    container: size,
    outerRing: size * 1.025,
    innerRing: size * 0.95,
    envelope: { w: size * 0.6, h: size * 0.4 },
    flap: { border: size * 0.15 },
    flyingEnvelopes: { container: size * 0.25, envelope: { w: size * 0.08, h: size * 0.05 } }
  };

  return (
    <div className="flex items-center space-x-4 relative">
      {/* Optimized CSS - only load once */}
      <style>{`
        @keyframes zeni-ring-pulse {
          0%, 100% { transform: scale(1); opacity: 0.95; }
          50% { transform: scale(1.03); opacity: 0.85; }
        }
        @keyframes zeni-border-rotate {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
        @keyframes zeni-envelope-float {
          0%, 100% { transform: translateY(0) rotateZ(10deg); }
          50% { transform: translateY(-2px) rotateZ(15deg); }
        }
        @keyframes zeni-flap-glow {
          0% { filter: brightness(1); opacity: 0.9; }
          100% { filter: brightness(1.15); opacity: 1; }
        }
        @keyframes zeni-envelope-fly {
          0% { 
            opacity: 0; 
            transform: scale(0.3) translate(0, 0) rotate(0deg); 
          }
          25% { 
            opacity: 1; 
            transform: scale(1) translate(${scale * 12}px, ${scale * -8}px) rotate(15deg); 
          }
          75% { 
            opacity: 0.8; 
            transform: scale(0.8) translate(${scale * 28}px, ${scale * -20}px) rotate(45deg); 
          }
          100% { 
            opacity: 0; 
            transform: scale(0.2) translate(${scale * 40}px, ${scale * -32}px) rotate(90deg); 
          }
        }
        @keyframes zeni-text-glow {
          0% { filter: brightness(1); }
          100% { filter: brightness(1.1); }
        }
        @keyframes bounceI {
          0%, 100% { transform: translateY(0); }
          50% { transform: translateY(-6px); }
        }
        .zeni-pause-animations * {
          animation-play-state: paused !important;
        }
      `}</style>

      {/* Logo Icon Container */}
      <div
        className={`relative flex items-center justify-center ${variant === 'static' ? 'zeni-pause-animations' : ''}`}
        style={{ width: dimensions.container, height: dimensions.container }}
      >
        {/* Animated Border Ring */}
        
        {/* Email Envelope */}
        <div
          className="relative bg-white rounded shadow-lg border border-gray-200 flex items-center justify-center overflow-hidden"
          style={{
            width: dimensions.envelope.w,
            height: dimensions.envelope.h,
            animation: variant === 'animated' ? 'zeni-envelope-float 3s ease-in-out infinite' : 'none',
            zIndex: 3,
          }}
        >
          {/* Envelope Background Gradient */}
          <div className="absolute inset-0 bg-gradient-to-br from-blue-50 via-white to-cyan-50 rounded" />
          
          {/* Envelope Flap - Fixed gradient colors */}
          <div
            className="absolute border-l-transparent border-r-transparent"
            style={{
              top: 0,
              left: '50%',
              transform: 'translateX(-50%)',
              borderLeftWidth: dimensions.flap.border,
              borderRightWidth: dimensions.flap.border,
              borderTopWidth: dimensions.flap.border * 0.6,
              borderTopColor: '#4facfe',
              animation: variant === 'animated' ? 'zeni-flap-glow 2.5s ease-in-out infinite alternate' : 'none',
              filter: 'drop-shadow(0 1px 2px rgba(0,0,0,0.1))',
            }}
          />
          
          {/* Subtle mail lines */}
          <div className="absolute inset-2 flex flex-col justify-center space-y-0.5">
            <div className="h-0.5 bg-gray-200 rounded w-3/4"></div>
            <div className="h-0.5 bg-gray-200 rounded w-1/2"></div>
          </div>
        </div>

        {/* Flying Mini Envelopes - Replacing the dots */}
        <div
          className="absolute"
          style={{
            top: dimensions.flyingEnvelopes.container * -0.5,
            right: dimensions.flyingEnvelopes.container * -0.5,
            width: dimensions.flyingEnvelopes.container,
            height: dimensions.flyingEnvelopes.container
          }}
        >
          {[
            { color: '#4facfe', delay: '0s' },
            { color: '#00f2fe', delay: '0.4s' },
            { color: '#667eea', delay: '0.8s' }
          ].map((envelope, i) => (
            <div key={i} className="absolute">
              {/* Flying Envelope Container */}
              <div
                className="relative"
                style={{
                  width: dimensions.flyingEnvelopes.envelope.w,
                  height: dimensions.flyingEnvelopes.envelope.h,
                  animation: variant === 'animated' ? `zeni-envelope-fly 3s ease-out infinite` : 'none',
                  animationDelay: envelope.delay,
                  top: i * (dimensions.flyingEnvelopes.envelope.h * 1.5),
                  left: (i % 2) * (dimensions.flyingEnvelopes.envelope.w * 0.5),
                }}
              >
                {/* Mini Envelope Body */}
                <div
                  className="absolute inset-0 rounded shadow-sm border"
                  style={{
                    backgroundColor: envelope.color,
                    borderColor: envelope.color,
                    opacity: 0.9
                  }}
                />
                
                {/* Mini Envelope Flap */}
                <div
                  className="absolute border-l-transparent border-r-transparent"
                  style={{
                    top: 0,
                    left: '50%',
                    transform: 'translateX(-50%)',
                    borderLeftWidth: dimensions.flyingEnvelopes.envelope.w * 0.25,
                    borderRightWidth: dimensions.flyingEnvelopes.envelope.w * 0.25,
                    borderTopWidth: dimensions.flyingEnvelopes.envelope.h * 0.4,
                    borderTopColor: envelope.color,
                    filter: 'brightness(1.1)',
                  }}
                />
                
                {/* Tiny mail indicator */}
                <div 
                  className="absolute bg-white rounded-full"
                  style={{
                    width: dimensions.flyingEnvelopes.envelope.w * 0.15,
                    height: dimensions.flyingEnvelopes.envelope.h * 0.2,
                    top: '60%',
                    left: '50%',
                    transform: 'translate(-50%, -50%)',
                    opacity: 0.8
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Typography Section */}
      <div className="flex flex-col items-start">
        {/* Typography */}
        <div className="font-bold flex items-baseline" style={{ fontSize: scale * 36, letterSpacing: scale * -1 }}>
          {/* Zeni with bouncing 'i' */}
          <span className="text-white drop-shadow-sm">Zen</span>
          <span
            className="text-green-500 inline-block"
            style={{
              animation: 'bounceI 1s ease-in-out infinite'
            }}
          >
            i
          </span>
          <span className="text-white drop-shadow-sm">Post</span>
        </div>
        
        {/* Professional Tagline */}
        {/* Tagline */}
        <div
          className="text-white/80 font-medium tracking-wide mt-1"
          style={{
            fontSize: scale * 14
          }}
        >
          Find Your Email Zen
        </div>
      </div>
    </div>
  );
}

