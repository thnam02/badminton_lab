import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// jsdom has no media playback or canvas drawing (node-environment tests have no DOM).
if (typeof HTMLMediaElement !== "undefined") {
  HTMLMediaElement.prototype.pause = function pause() {};
  HTMLMediaElement.prototype.play = function play() {
    return Promise.resolve();
  };
}
if (typeof HTMLCanvasElement !== "undefined") {
  HTMLCanvasElement.prototype.getContext = function getContext() {
    return null;
  } as typeof HTMLCanvasElement.prototype.getContext;
}

afterEach(() => {
  cleanup();
});
