<script setup lang="ts">
import { onLaunch, onShow } from '@dcloudio/uni-app'
import { appBootstrapper } from './src/services/AppBootstrapper'
import { syncManager } from './src/sync/syncManager'
import { applyStoredTheme, initializeTheme } from './src/theme/ThemeManager'
import { reminderService } from './src/services/ReminderService'
import { settingsRepository } from './src/repositories/SettingsRepository'

onLaunch(async () => {
  initializeTheme()
  try {
    await appBootstrapper.start()
    reminderService.apply(settingsRepository.get())
    void syncManager.initialize().catch((error) => console.warn('同步模块初始化失败，已保持离线模式', error))
  } catch (error) {
    console.error('应用初始化失败', error)
    uni.showToast({ title: '本地数据初始化失败', icon: 'none' })
  }
})

onShow(() => {
  applyStoredTheme()
  const syncConfig = syncManager.getConfig()
  if (!syncConfig.aiOnly && syncConfig.enableSync && syncConfig.autoSync) void syncManager.syncSafely('foreground')
})
</script>

<style>
@import "./styles/ui-theme.css";
@import "./styles/ui-components.css";
@import "./styles/ui-pages.css";
@import "./styles/ui-dashboard.css";
</style>
