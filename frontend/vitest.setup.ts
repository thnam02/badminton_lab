import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// jsdom has no media playback.
HTMLMediaElement.prototype.pause = function pause() {};
HTMLMediaElement.prototype.play = function play() {
  return Promise.resolve();
};

afterEach(() => {
  cleanup();
});
