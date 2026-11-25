// Each entry has an ink, two accents and a paper color. Store the four actual
// swatches with the issue so future library changes cannot recolor old covers.
const coverLibrary = {
  Newsstand: [
    ["Newsstand", "222020 B54035 F9C62D FAF1DB"],
    ["Field journal", "20362D 427D55 F4BD32 F9EBCD"],
    ["Signal red", "201F23 BD2E34 E9BA90 FAEEE1"],
    ["Sunday supplement", "172F40 297E9B F07C3D F6E9CB"],
    ["City edition", "192E41 F15149 81B3BF F2E7D5"],
    ["Letterpress", "362F30 874B61 CC9670 F0DAC0"],
  ],
  "Goosnav covers": [
    ["Weird fishes", "302747 EC258B 4978B2 F8D330"],
    ["Convention floor", "202831 EDA0C7 55A578 FFF7DC"],
    ["August heat", "312526 D73530 F3D628 509AC3"],
    ["Arcade flyer", "2C2251 F54792 33A9AA FAD67C"],
    ["Corner store", "2D3043 597DB8 DC5443 F5C268"],
    ["Bubblegum ink", "323355 CD4777 75BAB1 FADEA6"],
  ],
  "Warm & vintage": [
    ["Orange crate", "372923 CB5B28 DDA638 F9E6BA"],
    ["Desert motel", "483537 BF6451 69A5A0 F1D1A7"],
    ["Tobacco label", "332925 91602D D19A55 EFDBAC"],
    ["Brick & brass", "332B30 984242 BE984B E7D9B9"],
    ["Rose postcard", "4B3340 A35C65 D09B87 F9E7CF"],
    ["Copper kettle", "283F41 8E5543 C57B50 F0D6AD"],
  ],
  "Cool & quiet": [
    ["Tidal chart", "183B4A 40898B 93BAC0 E5EFE5"],
    ["Blue hour", "262D53 4E6399 9D8FC0 E5DEE9"],
    ["Mountain air", "1D3941 4B7178 B3BA91 EEECD9"],
    ["Chalk garden", "32433C 719379 BCB1A0 F3EDE0"],
    ["Winter coast", "243C56 467C9A A4C5CD F6ECDD"],
    ["Lavender fog", "38354F 777391 B7A0BB F4E9E3"],
  ],
  "Bright & playful": [
    ["Citrus stand", "193F3B 00A486 FFAB29 FCF2BE"],
    ["Roller rink", "282650 D64380 33AAC4 F5DA70"],
    ["Cherry soda", "36293D DA414D 51ABA1 F8E2BC"],
    ["Pool party", "23425C 009EB0 ED786B FCF4D3"],
    ["Toy catalog", "243859 387CC3 E95439 F7CB48"],
    ["Tangerine dream", "58304D C9496B F09346 FCE4A2"],
  ],
  "Dark & cinematic": [
    ["Midnight screen", "171E32 346482 BD526D EAD6BE"],
    ["Black orchid", "201C29 61385E AF776E ECD4B8"],
    ["Exit sign", "172724 466352 D16B4F F1DB9D"],
    ["Noir marquee", "25222B 544C60 BD8E52 EEE0BE"],
    ["After hours", "1D283B 485982 AB5763 D5C1AA"],
    ["Deep space", "181A35 564988 4F9699 EBD8AC"],
  ],
};
const printSwatches = {
  "Ink black": "#171717",
  "Paper white": "#FFFFFF",
  "Warm paper": "#F7EFDD",
  "Process cyan": "#00AEEF",
  "Process magenta": "#EC008C",
  "Process yellow": "#FFF200",
  "Cover yellow": "#F9C62D",
  Vermilion: "#DC4031",
  "Royal blue": "#264E9C",
};
const moodRecipes = {
  "From the artwork": [0.6, 0.51, 34],
  "Warm & vintage": [0.53, 0.49, 32],
  "Cool & quiet": [0.35, 0.47, -32],
  "Bright & playful": [0.81, 0.52, 126],
  "Dark & cinematic": [0.51, 0.36, 155],
};
function hslHex(h, s, l) {
  const channel = (n) => {
    const k = (n + (((h % 360) + 360) % 360) / 30) % 12;
    return Math.round(
      255 *
        (l - s * Math.min(l, 1 - l) * Math.max(-1, Math.min(k - 3, 9 - k, 1))),
    )
      .toString(16)
      .padStart(2, "0");
  };
  return ("#" + channel(0) + channel(8) + channel(4)).toUpperCase();
}
function artHue(hex) {
  const [r, g, b] = hex
    .match(/[a-f0-9]{2}/gi)
    .map((c) => parseInt(c, 16) / 255);
  const hi = Math.max(r, g, b),
    d = hi - Math.min(r, g, b);
  const phase =
    hi === r ? (g - b) / d : hi === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return { h: d ? (phase * 60 + 360) % 360 : 0, chroma: d };
}
function suggestCoverPalettes(source, mood, round) {
  const seeds = source.map(artHue).filter((c) => c.chroma > 0.12);
  const [sat, light, offset] = moodRecipes[mood];
  return Array.from({ length: 3 }, (_, n) => {
    const i = round * 3 + n;
    let hue = seeds.length ? seeds[i % seeds.length].h : [45, 202, 345][n];
    if (mood === "Warm & vintage")
      hue = 35 + Math.sin((hue * Math.PI) / 180) * 29;
    if (mood === "Cool & quiet")
      hue = 210 + Math.sin((hue * Math.PI) / 180) * 48;
    hue += i === 0 ? 0 : Math.sin(i * 2.39996) * 28;
    const alt = hue + offset + (i % 2 ? -13 : 13);
    const colors = [
      hslHex(hue, 0.29, 0.13),
      hslHex(alt, sat * 0.92, light),
      hslHex(hue, sat, Math.min(0.72, light + 0.08)),
      hslHex(hue + 20, 0.43, 0.91),
    ];
    if (
      mood === "From the artwork" &&
      i < source.length &&
      artHue(source[i]).chroma > 0.12
    )
      colors[2] = source[i];
    return { name: mood + " " + (i + 1), colors };
  });
}
