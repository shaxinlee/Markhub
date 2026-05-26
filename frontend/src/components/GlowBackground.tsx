/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useEffect, useState } from 'react';

export default function GlowBackground() {
  const [mousePosition, setMousePosition] = useState({ x: 0, y: 0 });

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      // Calculate normalized shifts
      const x = (e.clientX / window.innerWidth - 0.5) * 35;
      const y = (e.clientY / window.innerHeight - 0.5) * 35;
      setMousePosition({ x, y });
    };

    window.addEventListener('mousemove', handleMouseMove);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
    };
  }, []);

  return (
    <div className="absolute inset-0 pointer-events-none overflow-hidden z-0 bg-surface-container-low">
      {/* Luminous ambient glow 1 */}
      <div 
        className="absolute -bottom-24 -left-24 w-[600px] h-[600px] bg-tertiary-container/10 rounded-full blur-[140px] transition-transform duration-300 ease-out"
        style={{
          transform: `translate(${mousePosition.x}px, ${mousePosition.y}px)`,
        }}
      />
      {/* Luminous ambient glow 2 */}
      <div 
        className="absolute -bottom-48 right-1/4 w-[800px] h-[500px] bg-on-tertiary-container/10 rounded-full blur-[140px] transition-transform duration-300 ease-out"
        style={{
          transform: `translate(${-mousePosition.x * 1.5}px, ${-mousePosition.y * 1.5}px)`,
        }}
      />
    </div>
  );
}
