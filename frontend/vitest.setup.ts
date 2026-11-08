import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// jsdom has no media playback or canvas drawing.
HTMLMediaElement.prototype.pause = function pause() {};
HTMLMediaElement.prototype.play = function play() {
  return Promise.resolve();
};
HTMLCanvasElement.prototype.getContext = function getContext() {
  return null;
} as typeof HTMLCanvasElement.prototype.getContext;

afterEach(() => {
  cleanup();
});
