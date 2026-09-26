import { useEffect, useRef, type SVGProps } from 'react';

export function ZoomableSvg({ viewBox = '0 0 800 400', children, ...props }: SVGProps<SVGSVGElement>) {
  const ref = useRef<SVGSVGElement>(null);
  const reset = () => ref.current?.setAttribute('viewBox', viewBox);
  useEffect(() => {
    const svg = ref.current;
    if (!svg) return;
    const base = viewBox.split(/[ ,]+/).map(Number);
    svg.setAttribute('viewBox', viewBox);
    let pending = 0;
    const zoom = (factor: number, clientX?: number, clientY?: number) => {
      const v = svg.viewBox.baseVal;
      const matrix = svg.getScreenCTM();
      if (!matrix || !v.width) return;
      const cursor = clientX != null && clientY != null ? new DOMPoint(clientX, clientY).matrixTransform(matrix.inverse()) : new DOMPoint(v.x+v.width/2,v.y+v.height/2);
      const width = Math.max(base[2]/12, Math.min(base[2]*1.25, v.width*factor));
      const ratio = width/v.width;
      const next = [cursor.x-(cursor.x-v.x)*ratio,cursor.y-(cursor.y-v.y)*ratio,width,v.height*ratio];
      svg.setAttribute('viewBox',next.join(' '));
    };
    const wheel = (e: WheelEvent) => {
      e.preventDefault();
      const amount=e.deltaY*(e.deltaMode===1?16:e.deltaMode===2?300:1);
      cancelAnimationFrame(pending);
      pending=requestAnimationFrame(()=>zoom(Math.exp(Math.max(-.35,Math.min(.35,amount*.002))),e.clientX,e.clientY));
    };
    const key = (e: KeyboardEvent) => {
      if (e.key==='+' || e.key==='=' || e.key==='-') { e.preventDefault(); zoom(e.key==='-'?1.2:1/1.2); }
      if (e.key==='Home' || e.key==='0') { e.preventDefault(); svg.setAttribute('viewBox',viewBox); }
    };
    let drag: {
      id: number;
      x: number;
      y: number;
      view: [number, number, number, number];
      inverse: DOMMatrix | null;
      moved: boolean;
    } | null = null;
    let suppressClick = false;

    const onPointerDown = (e: PointerEvent) => {
      if (e.button !== 0 || !e.isPrimary) return;
      const matrix = svg.getScreenCTM();
      if (!matrix) return;
      const v = svg.viewBox.baseVal;
      suppressClick = false;
      drag = {
        id: e.pointerId,
        x: e.clientX,
        y: e.clientY,
        view: [v.x, v.y, v.width, v.height],
        inverse: matrix.inverse(),
        moved: false,
      };
    };

    const onPointerMove = (e: PointerEvent) => {
      if (!drag || e.pointerId !== drag.id) return;
      if (!(e.buttons & 1)) {
        endDrag();
        return;
      }
      const dx = e.clientX - drag.x;
      const dy = e.clientY - drag.y;
      if (!drag.moved && Math.hypot(dx, dy) < 4) return;
      if (!drag.moved) {
        drag.moved = true;
        suppressClick = true;
        try {
          svg.setPointerCapture(e.pointerId);
        } catch {}
        svg.classList.add('dragging');
      }
      e.preventDefault();
      if (drag.inverse) {
        const m = drag.inverse;
        const next = [
          drag.view[0] - m.a * dx - m.c * dy,
          drag.view[1] - m.b * dx - m.d * dy,
          drag.view[2],
          drag.view[3],
        ];
        svg.setAttribute('viewBox', next.join(' '));
      }
    };

    const endDrag = () => {
      if (!drag) return;
      const id = drag.id;
      drag = null;
      svg.classList.remove('dragging');
      try {
        if (svg.hasPointerCapture(id)) svg.releasePointerCapture(id);
      } catch {}
    };

    const onClickCapture = (e: MouseEvent) => {
      if (suppressClick && e.detail !== 0) {
        e.preventDefault();
        e.stopImmediatePropagation();
      }
    };

    const onDragStart = (e: DragEvent) => e.preventDefault();

    svg.addEventListener('wheel', wheel, { passive: false });
    svg.addEventListener('keydown', key);
    svg.addEventListener('pointerdown', onPointerDown);
    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', endDrag);
    window.addEventListener('pointercancel', endDrag);
    svg.addEventListener('lostpointercapture', endDrag);
    svg.addEventListener('click', onClickCapture, true);
    svg.addEventListener('dragstart', onDragStart);

    return () => {
      cancelAnimationFrame(pending);
      svg.removeEventListener('wheel', wheel);
      svg.removeEventListener('keydown', key);
      svg.removeEventListener('pointerdown', onPointerDown);
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerup', endDrag);
      window.removeEventListener('pointercancel', endDrag);
      svg.removeEventListener('lostpointercapture', endDrag);
      svg.removeEventListener('click', onClickCapture, true);
      svg.removeEventListener('dragstart', onDragStart);
    };
  }, [viewBox]);
  return (
    <div className="zoom-workspace">
      <div className="zoom-hint">
        <small>Kółko myszy: przybliż / oddal · przeciągnij lewym przyciskiem: przesuń · klawisze + / −</small>
        <button onClick={reset}>Resetuj widok</button>
      </div>
      <svg {...props} ref={ref} viewBox={viewBox} tabIndex={0} onDoubleClick={reset}>
        {children}
      </svg>
    </div>
  );
}
