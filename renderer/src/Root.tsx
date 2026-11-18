import React from "react";
import { Composition } from "remotion";
import { Overlay } from "./Overlay";
import { EMPTY, OverlayProps } from "./types";

export const Root: React.FC = () => (
  <Composition
    id="Overlay"
    component={Overlay}
    defaultProps={EMPTY}
    durationInFrames={EMPTY.duration_f}
    fps={EMPTY.fps}
    width={EMPTY.width}
    height={EMPTY.height}
    calculateMetadata={({ props }: { props: OverlayProps }) => ({
      durationInFrames: props.duration_f,
      fps: props.fps,
      width: props.width,
      height: props.height,
    })}
  />
);
