import { describe, it, expect } from 'vitest';
import { entryAt, entryLabel, parseOutline, prettyPlace, sceneCaption, targetAt, targetLabel, type OutlineWords } from './outline';

const WORDS: OutlineWords = { page: 'Page {n}', uncutPage: 'Uncut page {n}', noPlace: 'No place', panel: 'Panel', scene: 'Scene' };

// from scripts/rooftop-static.comic (Comics repo)
const ROOFTOP = [
  '// A two-page Second Floor short: Nova fixes the building\'s rooftop speaker, Mara brings coffee.',   // 1
  'title: Rooftop Static',                                                                               // 2
  'seed: 4100',                                                                                          // 3
  '',                                                                                                    // 4
  'PAGE',                                                                                                // 5
  'layout: 1-2',                                                                                         // 6
  '',                                                                                                    // 7
  'PANEL h=1.2',                                                                                         // 8
  'place: rooftop, evening',                                                                             // 9
  'shot: establishing',                                                                                  // 10
  'Apartment building rooftop at golden hour, string lights not yet lit, an old loudspeaker on a pole, toolbox open on the gravel.',   // 11
  'CAPTION: Second Floor. Friday, just before sunset.',                                                  // 12
  'SFX (tr): KRZZT',                                                                                     // 13
  '',                                                                                                    // 14
  'PANEL',                                                                                               // 15
  'cast: nova(work, determined, holding a screwdriver)',                                                 // 16
  'shot: medium',                                                                                        // 17
  'Nova kneeling beside an old loudspeaker, its back panel open, wires everywhere.',                     // 18
  'NOVA: Come on. One more song. *That\'s* all I\'m asking.',                                            // 19
  '',                                                                                                    // 20
  'PAGE',                                                                                                // 21
  'layout: 2-1',                                                                                         // 22
  '',                                                                                                    // 23
  '// narrow panel: one character on screen, the other speaks from off-panel',                          // 24
  'PANEL',                                                                                               // 25
  'cast: nova(work, tired, holding a coffee mug)',                                                       // 26
  'shot: medium',                                                                                        // 27
  'Nova sitting on the rooftop ledge with a mug of coffee in both hands, city skyline at sunset behind her.',   // 28
  'MARA (off, left): Half the building thinks you\'re building a radio telescope.',                     // 29
  '',                                                                                                    // 30
  '// seed picked from --variants',                                                                      // 31
  'PANEL h=1.3 seed=28060',                                                                              // 32
  'place: rooftop, night',                                                                               // 33
  'cast: nova(work, smile), mara(casual, smile)',                                                        // 34
  'shot: wide',                                                                                          // 35
  'Two women sitting side by side on the flat rooftop ledge, string lights glowing overhead.',           // 36
  'NOVA (shout): IT WORKS!',                                                                             // 37
].join('\n');

// from scripts/jade-and-haile-ep2.comic (Comics repo), shortened; its uncut todo page, and a PANEL uncut added
const JADE = [
  'title: Jade & Haile',                                    // 1
  'seed: 5700',                                             // 2
  '',                                                       // 3
  'PAGE 3 — Practice and a Portrait',                       // 4
  'layout: 1-1-1-1',                                        // 5
  '',                                                       // 6
  'PANEL',                                                  // 7
  'place: gym, day',                                        // 8
  'cast: jade(jacket, smile, sitting on the bleachers), haile(jersey, smirk, standing on the court, holding a volleyball)',   // 9
  'shot: wide',                                             // 10
  'The volleyball court; Jade sitting on the wooden bleachers on the left, Haile in her number 4 jersey on the court on the right, holding a volleyball.',   // 11
  'JADE: You\'re ridiculous at this.',                      // 12
  '',                                                       // 13
  'PANEL',                                                  // 14
  'place: apartment, evening',                              // 15
  'cast: jade(wearing grey hoodie and baggy light blue jeans, smirk), haile(tank, neutral)',   // 16
  'shot: wide',                                             // 17
  'Two women sitting across a small wooden table in a lamplit living room.',   // 18
  '',                                                       // 19
  '// uncut slot: after the evening kiss',                  // 20
  'PAGE uncut todo',                                        // 21
  'layout: 1-2',                                            // 22
  '',                                                       // 23
  'PANEL',                                                  // 24
  'place: apartment, evening',                              // 25
  'cast: jade(wearing grey hoodie and baggy light blue jeans), haile(tank)',   // 26
  '// TODO: describe the panel',                            // 27
  '',                                                       // 28
  'PANEL',                                                  // 29
  'cast: jade(wearing grey hoodie and baggy light blue jeans), haile(tank)',   // 30
  '// TODO: describe the panel',                            // 31
  '',                                                       // 32
  'PAGE 4 — Between Places',                                // 33
  'layout: 1-1-2',                                          // 34
  '',                                                       // 35
  'PANEL',                                                  // 36
  'cast: jade(wearing grey hoodie and baggy light blue jeans, smile, sitting on the sofa), haile(hoodie, neutral)',   // 37
  'shot: wide',                                             // 38
  'Evening in the living room.',                            // 39
  'CAPTION: The next morning, ordinary things felt unexpectedly new.',   // 40
  '',                                                       // 41
  'PANEL uncut h=1.2',                                      // 42
  'place: park, evening',                                   // 43
  'cast: jade(jacket)',                                     // 44
  'Jade by the creek.',                                     // 45
  '',                                                       // 46
  'PANEL',                                                  // 47
  'cast: jade(jacket, neutral, walking, seen from behind)', // 48
  'HAILE: Practice.',                                       // 49
  'CAPTION: That night, nothing.',                          // 50
  '',                                                       // 51
  'PANEL uncut todo',                                       // 52
  'cast: jade(jacket)',                                     // 53
].join('\n');

const offsetOfLine = (text: string, line: number) => text.split('\n').slice(0, line - 1).reduce((n, l) => n + l.length + 1, 0);
const slice = (text: string, e: { startOffset: number; endOffset: number }) => text.slice(e.startOffset, e.endOffset);

describe('parseOutline', () => {
  it('lists pages and panels with whole-line blocks', () => {
    const o = parseOutline(ROOFTOP);
    expect(o.pages.map(p => p.id)).toEqual(['1', '2']);
    expect(o.pages[0]).toMatchObject({ n: 1, startLine: 5, endLine: 20, panels: ['1.1', '1.2'], uncut: false, title: '' });
    expect(slice(ROOFTOP, o.pages[0]).startsWith('PAGE\nlayout: 1-2\n')).toBe(true);
    expect(slice(ROOFTOP, o.pages[0]).endsWith('asking.\n\n')).toBe(true);
    expect(o.panels.map(p => p.id)).toEqual(['1.1', '1.2', '2.1', '2.2']);
    const [a, b, c, d] = o.panels;
    expect(a).toMatchObject({ line: 8, endLine: 14, shot: 'establishing', cast: [], place: 'rooftop', time: 'evening', ownPlace: true });
    expect(slice(ROOFTOP, a)).toBe(ROOFTOP.split('\n').slice(7, 14).join('\n') + '\n');
    expect(a.firstDescription.length).toBeLessThanOrEqual(80);
    expect(a.firstDescription.endsWith('…')).toBe(true);
    expect(b).toMatchObject({ line: 15, endLine: 20, cast: ['nova'], firstDescription: 'Nova kneeling beside an old loudspeaker, its back panel open, wires everywhere.' });
    // the comments before a PANEL belong to the block before it, as in the AI popover's own detection
    expect(c).toMatchObject({ line: 25, endLine: 31, place: 'rooftop', time: 'evening', ownPlace: false });
    expect(d).toMatchObject({ line: 32, endLine: 37, cast: ['nova', 'mara'], shot: 'wide', time: 'night' });
    expect(d.endOffset).toBe(ROOFTOP.length);   // the last panel runs to the end
  });

  it('carries the place over and splits scenes on a time change', () => {
    const o = parseOutline(ROOFTOP);
    expect(o.scenes.map(s => [s.place, s.time, s.panels])).toEqual([
      ['rooftop', 'evening', ['1.1', '1.2', '2.1']],
      ['rooftop', 'night', ['2.2']],
    ]);
    // a scene across a page break holds the next page's header, from its first panel's start to its last panel's end
    const s1 = o.scenes[0];
    expect(s1).toMatchObject({ startLine: 8, endLine: 31, cast: ['nova'] });
    expect(slice(ROOFTOP, s1)).toContain('PAGE\nlayout: 2-1');
    expect(entryLabel('scene', s1, WORDS)).toBe('Rooftop, evening · 1.1–2.1');
    expect(entryLabel('scene', o.scenes[1], WORDS)).toBe('Rooftop, night · 2.2');
  });

  it('gives uncut pages and panels comic.js ids, todo flags and their own scenes', () => {
    const o = parseOutline(JADE);
    expect(o.pages.map(p => [p.id, p.title, p.uncut, p.todo])).toEqual([
      ['1', 'Practice and a Portrait', false, false],
      ['u1', '', true, true],
      ['2', 'Between Places', false, false],
    ]);
    expect(entryLabel('page', o.pages[0], WORDS)).toBe('Page 1 — Practice and a Portrait');   // "PAGE 3" counts as page 1
    expect(entryLabel('page', o.pages[1], WORDS)).toBe('Uncut page 1');
    expect(o.panels.map(p => [p.id, p.uncut, p.todo])).toEqual([
      ['1.1', false, false], ['1.2', false, false],
      ['u1.1', true, true], ['u1.2', true, true],
      ['2.1', false, false], ['2.u1', true, false], ['2.2', false, false], ['2.u2', true, true],
    ]);
    const byId = Object.fromEntries(o.panels.map(p => [p.id, p]));
    // a regular panel's place comes from the regular panel before it, never from an uncut one...
    expect(byId['2.1']).toMatchObject({ place: 'apartment', time: 'evening' });
    expect(byId['2.2']).toMatchObject({ place: 'apartment', time: 'evening' });
    // ...an uncut one's from the panel before it in the script
    expect(byId['u1.2']).toMatchObject({ place: 'apartment', time: 'evening' });
    expect(byId['2.u2']).toMatchObject({ place: 'apartment', time: 'evening' });
    expect(byId['2.u1']).toMatchObject({ place: 'park', time: 'evening' });
    expect(o.scenes.map(s => s.panels)).toEqual([
      ['1.1'],                 // gym, day
      ['1.2'],                 // apartment, evening
      ['u1.1', 'u1.2'],        // the uncut page: a scene of its own though the place is the same
      ['2.1'],                 // "The next morning": a caption scene change
      ['2.u1'],                // park
      ['2.2', '2.u2'],         // "That night"
    ]);
    expect(o.scenes[2]).toMatchObject({ uncut: true, todo: true, cast: ['jade', 'haile'] });
    expect(o.scenes[3]).toMatchObject({ uncut: false, todo: false });
    expect(byId['2.1'].captionBreak).toBe(true);
    // the caption must open the panel's lettering
    expect(byId['2.2'].captionBreak).toBe(false);
  });

  it('works on CRLF text with the same offsets a textarea would give', () => {
    const crlf = JADE.replace(/\n/g, '\r\n');
    const o = parseOutline(crlf);
    const lf = parseOutline(JADE);
    expect(o.panels.map(p => [p.id, p.line, p.place, p.cast.join()])).toEqual(lf.panels.map(p => [p.id, p.line, p.place, p.cast.join()]));
    const p = o.panels[0];
    expect(slice(crlf, p).startsWith('PANEL\r\nplace: gym, day\r\n')).toBe(true);
    expect(slice(crlf, p).endsWith('\r\n\r\n')).toBe(true);
    expect(o.pages[0].title).toBe('Practice and a Portrait');
    expect(o.scenes.map(s => s.panels)).toEqual(lf.scenes.map(s => s.panels));
  });

  it('counts UTF-16 code units', () => {
    const text = 'PAGE\nPANEL\nplace: café, day\nSFX: ♪ 🎵\n\nPANEL\nshot: wide\n';
    const o = parseOutline(text);
    expect(o.panels[1].startOffset).toBe(text.indexOf('PANEL\nshot'));
    expect(slice(text, o.panels[0])).toBe('PANEL\nplace: café, day\nSFX: ♪ 🎵\n\n');
    expect(o.scenes.length).toBe(1);   // the second panel carries café, day over
  });

  it('never throws on partial or invalid text', () => {
    for (const text of ['', '\n\n', 'PANEL\nno page', 'PAGE', 'PAGE uncut todo\nPANEL uncut todo\nPANEL', 'title: x\nPAGE\nPANEL\ncast: (((,,\nplace: ,\nplace:\n', 'PAGEANT\nPANELS', '\u0000￿\uD800', 'PAGE\r\n\r\nPANEL\r']) {
      expect(() => parseOutline(text)).not.toThrow();
    }
    expect(parseOutline('PANEL\nno page').panels).toEqual([]);
    expect(parseOutline('PAGEANT\nPANELS').pages).toEqual([]);
    const o = parseOutline('PAGE\nPANEL\ncast: (((,,\nplace: ,\n');
    expect(o.panels[0]).toMatchObject({ cast: [], place: null });
    expect(entryLabel('scene', o.scenes[0], WORDS)).toBe('No place · 1.1');
  });

  it('is memoised per text', () => {
    expect(parseOutline(ROOFTOP)).toBe(parseOutline(ROOFTOP));
  });

  it('parses a large script in linear time', () => {
    const big = Array.from({ length: 400 }, () => ROOFTOP.split('\n').slice(4).join('\n')).join('\n') + `\n// ${Math.random()}`;
    const t0 = performance.now();
    const o = parseOutline(big);
    expect(o.panels.length).toBe(1600);
    expect(performance.now() - t0).toBeLessThan(500);
  });
});

describe('sceneCaption', () => {
  it('reads a time jump or a cut as a scene change', () => {
    for (const s of ['Later.', 'Much later', 'Hours later, the rain stopped.', 'A few days later, I was still wondering.', 'Two weeks on.',
      'That night.', 'The next morning, ordinary things felt new.', 'Next day', 'The following week', 'Meanwhile, at the gym…',
      'Elsewhere.', 'Monday.', 'On Friday, we met.', '— 7:40 a.m.', '7:40 AM', '"Later," she said.']) {
      expect(sceneCaption(s), s).toBe(true);
    }
    for (const s of ['I later went home.', 'Second Floor. Friday, just before sunset.', 'Laterally speaking', 'Mondayish weather', 'Sundaes for everyone',
      'We were beginning to understand.', 'She came later.', '1234']) {
      expect(sceneCaption(s), s).toBe(false);
    }
  });
});

describe('targetAt (the AI popover target)', () => {
  const o = parseOutline(JADE);
  const at = (line: number, col = 0) => offsetOfLine(JADE, line) + col;

  it('finds the panel, scene and page around the caret', () => {
    expect(targetAt(o, at(11, 5), 'panel')?.entry.id).toBe('1.1');
    expect(targetAt(o, at(11, 5), 'scene')?.entry.id).toBe('s1');
    expect(targetAt(o, at(11, 5), 'page')?.entry.id).toBe('1');
    const scene = targetAt(o, at(26), 'scene')!;
    expect(scene).toMatchObject({ kind: 'scene', start: at(24), end: at(33) });
    expect(targetLabel(scene, WORDS)).toBe('Scene: Apartment, evening · u1.1–u1.2');
    expect(targetLabel(targetAt(o, at(26), 'panel')!, WORDS)).toBe('Panel u1.1');
    expect(targetLabel(targetAt(o, at(26), 'page')!, WORDS)).toBe('Uncut page 1');
  });

  it('re-targets around the same caret when the kind changes', () => {
    const caret = at(48, 3);   // in 2.2
    const kinds = ['panel', 'scene', 'page'] as const;
    const got = kinds.map(k => targetAt(o, caret, k)!);
    expect(got.map(t => t.entry.id)).toEqual(['2.2', 's6', '2']);
    expect(got[0].start).toBe(at(47));
    expect(got[1]).toMatchObject({ start: at(47), end: JADE.length });
    expect(got[2]).toMatchObject({ start: at(33), end: JADE.length });
    // each one holds the caret
    for (const t of got) expect(t.start <= caret && caret <= t.end).toBe(true);
  });

  it('takes the page\'s first panel on a PAGE line, and nothing in the script header', () => {
    expect(targetAt(o, at(34), 'panel')?.entry.id).toBe('2.1');
    expect(targetAt(o, at(34), 'scene')?.entry.id).toBe('s4');
    expect(targetAt(o, at(34), 'page')?.entry.id).toBe('2');
    for (const k of ['panel', 'scene', 'page'] as const) expect(targetAt(o, at(1), k)).toBeNull();
    // a page without panels has no panel or scene to target
    const bare = parseOutline('PAGE\nlayout: 1\n');
    expect(targetAt(bare, 2, 'panel')).toBeNull();
    expect(targetAt(bare, 2, 'scene')).toBeNull();
    expect(targetAt(bare, 2, 'page')?.entry.id).toBe('1');
  });

  it('treats the caret at the very end as inside the last block', () => {
    expect(targetAt(o, JADE.length, 'panel')?.entry.id).toBe('2.u2');
    expect(entryAt(o.panels, JADE.length, JADE.length)?.id).toBe('2.u2');
    expect(entryAt(o.panels, at(7) - 1, JADE.length)).toBeNull();   // the header
  });
});

describe('prettyPlace', () => {
  it('capitalises and spaces place keys', () => {
    expect(prettyPlace('cafe')).toBe('Cafe');
    expect(prettyPlace('sand_court')).toBe('Sand court');
    expect(prettyPlace('')).toBe('');
  });
});
