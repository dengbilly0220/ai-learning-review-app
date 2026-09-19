/// <reference types="@dcloudio/types" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<Record<string, unknown>, Record<string, unknown>, unknown>
  export default component
}

// HBuilderX 会在 App 构建时解析 UTS 插件；该声明同时让标准 TypeScript 检查器认识插件入口。
declare module '*/uni_modules/gongkao-reminder' {
  export function scheduleDailyReminder(hour: number, minute: number): boolean
  export function cancelDailyReminder(): boolean
  export function showTestReminder(): boolean
}
