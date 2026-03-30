export interface PackageCard {
  id: string
  name: string
  tag: string
  cat: string
  img: string
  hot?: boolean
  svip?: boolean
}

export const packageCards: PackageCard[] = [
  {
    id: 'minimal',
    name: '极简高定棚拍',
    tag: '棚拍 · 极简 · 高级感',
    cat: '棚拍',
    img: '/images/package-minimal.png',
  },
  {
    id: 'iceland',
    name: '冰岛黑沙滩史诗',
    tag: '旅拍 · 史诗 · 大片感',
    cat: '旅拍',
    hot: true,
    img: '/images/package-iceland.png',
  },
  {
    id: 'cyberpunk',
    name: '中式赛博朋克',
    tag: '中式 · 赛博 · 未来感',
    cat: '中式',
    img: '/images/package-cyberpunk.png',
  },
  {
    id: 'french',
    name: '法式街角胶片',
    tag: '胶片 · 法式 · 浪漫',
    cat: '胶片',
    img: '/images/package-french.png',
  },
  {
    id: 'onsen',
    name: '日式温泉旅拍',
    tag: '旅拍 · 温泉 · 清透',
    cat: '旅拍',
    img: '/images/package-onsen.png',
  },
  {
    id: 'starcamp',
    name: '星空露营婚纱',
    tag: '奇幻 · 星空 · 梦幻',
    cat: '奇幻',
    svip: true,
    img: '/images/package-starcamp.png',
  },
]
