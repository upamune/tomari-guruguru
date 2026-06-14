// キャラクター設定 — Web版で切り替えるキャラとスライス画像の参照先を一元管理

const sharedSheets = {
  eyesOpen: { close: 'A', half: 'B', open: 'C' },
  eyesClosed: { close: 'D', half: 'E', open: 'F' },
};

const characters = [
  {
    id: 'upamune',
    label: 'upamune',
    basePath: 'characters/upamune/slices',
    ext: 'webp',
  },
  {
    id: 'michiru_da',
    label: 'michiru_da',
    basePath: 'characters/michiru_da/slices',
    ext: 'webp',
  },
];

function getCharacter(id) {
  return characters.find((character) => character.id === id) || characters[0];
}

function src(character, sheet, r, c) {
  return `${character.basePath}/${sheet}/r${r}c${c}.${character.ext}`;
}

export default {
  rows: 5,
  cols: 5,
  sheets: sharedSheets,
  characters,
  defaultCharacterId: characters[0].id,
  getCharacter,
  src,
};
