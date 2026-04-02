export type PackageCategory = 'chinese' | 'western' | 'artistic' | 'travel'

export const packageTabs = ['中式', '西式', '旅拍', '夜景', '影棚', '幻境'] as const
export type PackageTab = (typeof packageTabs)[number]

export interface PackageCard {
  id: string
  name: string
  tag: string
  category: PackageCategory
  img: string
  description: string
  tracks: PackageTab[]
  wardrobes: string[]
  scenes: string[]
  badge?: '热门' | '推荐'
}

export interface DirectionOption {
  id: string
  label: string
  matches: string[]
}

export const wardrobeOptions: DirectionOption[] = [
  {
    id: 'main_gown',
    label: '主纱 / 缎面礼服',
    matches: ['minimal', 'western-romantic', 'iceland', 'french', 'travel-destination'],
  },
  {
    id: 'qipao',
    label: '旗袍 / 中山装',
    matches: ['chinese-classic'],
  },
  {
    id: 'xiuhe',
    label: '秀禾龙凤褂',
    matches: ['chinese-classic'],
  },
  {
    id: 'light_formal',
    label: '轻礼服 / 西装',
    matches: ['french', 'travel-destination', 'western-romantic'],
  },
]

export const sceneOptions: DirectionOption[] = [
  {
    id: 'studio',
    label: '影棚',
    matches: ['minimal'],
  },
  {
    id: 'coast',
    label: '海边',
    matches: ['iceland'],
  },
  {
    id: 'street',
    label: '街巷 / 古镇',
    matches: ['french', 'travel-destination'],
  },
  {
    id: 'garden',
    label: '花园 / 草坪',
    matches: ['western-romantic'],
  },
  {
    id: 'courtyard',
    label: '庭院 / 夜宴',
    matches: ['chinese-classic'],
  },
]

export const packageCards: PackageCard[] = [
  {
    id: 'minimal',
    name: '西式极简影棚',
    tag: '西式 · 主纱西装 · 影棚',
    category: 'western',
    img: '/images/generated-1774933175666.png',
    description: '留白影棚、干净构图，适合先把服饰轮廓和人物质感定住。',
    tracks: ['西式', '影棚'],
    wardrobes: ['主纱 / 缎面礼服'],
    scenes: ['影棚'],
  },
  {
    id: 'iceland',
    name: '海岸礁石誓约',
    tag: '海岸风景 · 西式礼服 · 海边',
    category: 'travel',
    img: '/images/package-iceland.png',
    description: '黑沙滩与海风做主叙事，适合做史诗感与双人比例锚定。',
    tracks: ['旅拍', '西式'],
    wardrobes: ['主纱 / 缎面礼服'],
    scenes: ['海边'],
    badge: '热门',
  },
  {
    id: 'french',
    name: '法式街角胶片',
    tag: '街角漫步 · 胶片质感 · 法式旅拍',
    category: 'western',
    img: '/images/package-french.png',
    description: '偏生活感的旅拍语境，适合轻松、松弛、像真实情侣纪录片。',
    tracks: ['旅拍', '西式'],
    wardrobes: ['主纱 / 缎面礼服', '轻礼服 / 西装'],
    scenes: ['街巷 / 古镇'],
  },
  {
    id: 'travel-destination',
    name: '城光街巷漫步',
    tag: '旅拍 · 城市街巷 · 轻松漫游',
    category: 'travel',
    img: '/images/generated-1773760935669.png',
    description: '旧城街巷与纪实步行感更强，适合把“像一起旅行”做成主情绪。',
    tracks: ['旅拍'],
    wardrobes: ['主纱 / 缎面礼服', '轻礼服 / 西装'],
    scenes: ['街巷 / 古镇'],
  },
  {
    id: 'western-romantic',
    name: '旷野夕光誓约',
    tag: '日落草坪 · 轻野浪漫 · 户外仪式',
    category: 'western',
    img: '/images/generated-1773760974366.png',
    description: '更偏柔光与仪式感，适合做暮色草坪、花园誓言和轻野婚礼氛围。',
    tracks: ['西式', '旅拍'],
    wardrobes: ['主纱 / 缎面礼服', '轻礼服 / 西装'],
    scenes: ['花园 / 草坪'],
    badge: '推荐',
  },
  {
    id: 'chinese-classic',
    name: '东方庭院鎏金',
    tag: '东方庭院 · 新中式礼服 · 夜宴氛围',
    category: 'chinese',
    img: '/images/generated-1774966617754-fixed.png',
    description: '灯笼、庭院和金红配色更完整，适合做高定中式与礼序氛围。',
    tracks: ['中式', '夜景'],
    wardrobes: ['旗袍 / 中山装', '秀禾龙凤褂'],
    scenes: ['庭院 / 夜宴'],
  },
]

export function getPackageCard(id: string): PackageCard | null {
  return packageCards.find(item => item.id === id) ?? null
}
