/**
 * Phone width, where the search panel is a top bar and the place card a
 * bottom sheet over the map. CSS cannot import it: every `max-width` media
 * query under src/ spells it out, and layout.test.ts holds them to this.
 */
export const PHONE_MEDIA = '(max-width: 600px)';

/**
 * A finger for a pointer: bigger hit boxes and tap targets, and the system
 * share sheet. Like PHONE_MEDIA, every `pointer` media query under src/
 * spells it out, and layout.test.ts holds them to this.
 */
export const TOUCH_MEDIA = '(pointer: coarse)';
