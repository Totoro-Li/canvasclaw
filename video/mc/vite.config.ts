import {defineConfig} from 'vite';
import {createRequire} from 'module';

const require = createRequire(import.meta.url);
const motionCanvas = require('@motion-canvas/vite-plugin').default;
const ffmpeg = require('@motion-canvas/ffmpeg').default;

export default defineConfig({
  plugins: [motionCanvas(), ffmpeg()],
});
