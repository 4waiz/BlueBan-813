"use client";
/**
 * React Three Fiber <Canvas> that stays full-size and clickable when the page
 * is scaled with CSS zoom (globals.css draws the whole interface at 90 % on
 * laptop-sized screens).
 *
 * Under CSS zoom an element's on-screen rectangle is smaller than its own CSS
 * size. The stock Canvas sizes itself from the on-screen rectangle (so it
 * would draw 10 % short of its panel) and maps the pointer with offsetX (so
 * picks would drift). This wrapper measures the container in its own CSS
 * pixels and maps the pointer from the on-screen rectangle, which is right at
 * any zoom.
 */
import React from "react";
import { Canvas } from "@react-three/fiber";

type Props = React.ComponentProps<typeof Canvas>;

export default function ZoomCanvas({ resize, onCreated, ...props }: Props) {
  return (
    <Canvas
      {...props}
      resize={{ offsetSize: true, ...resize }}
      onCreated={(state) => {
        state.setEvents({
          compute: (event, s) => {
            const r = s.gl.domElement.getBoundingClientRect();
            s.pointer.set(((event.clientX - r.left) / r.width) * 2 - 1, -((event.clientY - r.top) / r.height) * 2 + 1);
            s.raycaster.setFromCamera(s.pointer, s.camera);
          },
        });
        onCreated?.(state);
      }}
    />
  );
}
