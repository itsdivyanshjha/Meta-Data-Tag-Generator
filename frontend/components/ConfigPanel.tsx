'use client'

import { TaggingConfig, AVAILABLE_MODELS } from '@/lib/types'

interface ConfigPanelProps {
  config: TaggingConfig
  setConfig: (config: TaggingConfig) => void
}

export default function ConfigPanel({ config, setConfig }: ConfigPanelProps) {
  return (
    <div className="glass-card p-6 space-y-6 sticky top-24">
      <div className="flex items-center gap-3 pb-4 border-b border-slate-200 dark:border-slate-700">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-slate-600 to-slate-800 flex items-center justify-center">
          <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
        </div>
        <div>
          <h2 className="text-lg font-bold text-slate-800 dark:text-white">Configuration</h2>
          <p className="text-sm text-slate-500 dark:text-slate-400">Customize your tagging settings</p>
        </div>
      </div>
      
      <div className="space-y-5">
        {/* API Key */}
        <div className="space-y-2">
          <label className="flex items-center gap-2 text-sm font-medium text-slate-700 dark:text-slate-300">
            <svg className="w-4 h-4 text-sky-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
            </svg>
            OpenRouter API Key
          </label>
          <input
            type="password"
            value={config.api_key}
            onChange={(e) => setConfig({...config, api_key: e.target.value})}
            placeholder="sk-or-v1-..."
            className="input-field text-sm"
          />
          <p className="text-xs text-slate-500 dark:text-slate-400 flex items-center gap-1">
            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            Get your key at{' '}
            <a 
              href="https://openrouter.ai/keys" 
              target="_blank" 
              rel="noopener noreferrer"
              className="text-sky-600 dark:text-sky-400 hover:underline"
            >
              openrouter.ai/keys
            </a>
          </p>
        </div>

        {/* Model Selection */}
        <div className="space-y-2">
          <label className="flex items-center gap-2 text-sm font-medium text-slate-700 dark:text-slate-300">
            <svg className="w-4 h-4 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
            AI Model
          </label>
          <select
            value={config.model_name}
            onChange={(e) => setConfig({...config, model_name: e.target.value})}
            className="input-field text-sm"
          >
            {AVAILABLE_MODELS.map(model => (
              <option key={model.id} value={model.id}>
                {model.name} ({model.provider})
              </option>
            ))}
          </select>
        </div>

        {/* Number of Pages */}
        <div className="space-y-3">
          <label className="flex items-center justify-between text-sm font-medium text-slate-700 dark:text-slate-300">
            <span className="flex items-center gap-2">
              <svg className="w-4 h-4 text-emerald-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 13a2 2 0 01-2-2V7m2 13a2 2 0 002-2V9a2 2 0 00-2-2h-2m-4-3H9M7 16h6M7 8h6v4H7V8z" />
              </svg>
              Pages to Extract
            </span>
            <span className="text-sky-600 dark:text-sky-400 font-semibold bg-sky-50 dark:bg-sky-900/30 px-2 py-0.5 rounded-md">
              {config.num_pages}
            </span>
          </label>
          <input
            type="range"
            min="1"
            max="10"
            value={config.num_pages}
            onChange={(e) => setConfig({...config, num_pages: parseInt(e.target.value)})}
            className="w-full h-2 bg-slate-200 dark:bg-slate-700 rounded-lg appearance-none cursor-pointer accent-sky-500"
          />
          <div className="flex justify-between text-xs text-slate-400">
            <span>1 page</span>
            <span>10 pages</span>
          </div>
        </div>

        {/* Number of Tags */}
        <div className="space-y-3">
          <label className="flex items-center justify-between text-sm font-medium text-slate-700 dark:text-slate-300">
            <span className="flex items-center gap-2">
              <svg className="w-4 h-4 text-purple-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A2 2 0 013 12V7a4 4 0 014-4z" />
              </svg>
              Tags to Generate
            </span>
            <span className="text-sky-600 dark:text-sky-400 font-semibold bg-sky-50 dark:bg-sky-900/30 px-2 py-0.5 rounded-md">
              {config.num_tags}
            </span>
          </label>
          <input
            type="range"
            min="3"
            max="15"
            value={config.num_tags}
            onChange={(e) => setConfig({...config, num_tags: parseInt(e.target.value)})}
            className="w-full h-2 bg-slate-200 dark:bg-slate-700 rounded-lg appearance-none cursor-pointer accent-sky-500"
          />
          <div className="flex justify-between text-xs text-slate-400">
            <span>3 tags</span>
            <span>15 tags</span>
          </div>
        </div>
      </div>

      {/* Status indicator */}
      <div className={`flex items-center gap-2 p-3 rounded-xl ${
        config.api_key 
          ? 'bg-emerald-50 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-400' 
          : 'bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400'
      }`}>
        <div className={`w-2 h-2 rounded-full ${config.api_key ? 'bg-emerald-500' : 'bg-amber-500'} animate-pulse`} />
        <span className="text-sm font-medium">
          {config.api_key ? 'Ready to process' : 'API key required'}
        </span>
      </div>
    </div>
  )
}

