'use client'

import { TaggingConfig } from '@/lib/types'

interface ConfigPanelProps {
  config: TaggingConfig
  setConfig: (config: TaggingConfig) => void
}

export default function ConfigPanel({ config, setConfig }: ConfigPanelProps) {
  return (
    <div className="card p-6 space-y-6">
      <h2 className="text-lg font-bold text-gray-900">Configuration</h2>
      
      <div className="space-y-4">
        {/* API Key */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            OpenRouter API Key
          </label>
          <input
            type="password"
            value={config.api_key}
            onChange={(e) => setConfig({...config, api_key: e.target.value})}
            placeholder="sk-or-v1-..."
            className="input-field"
          />
          <p className="text-xs text-gray-500 mt-1">
            Get your key at{' '}
            <a 
              href="https://openrouter.ai/keys" 
              target="_blank" 
              rel="noopener noreferrer"
              className="text-blue-600 hover:underline"
            >
              openrouter.ai/keys
            </a>
          </p>
        </div>

        {/* Model Name */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Model Name
          </label>
          <input
            type="text"
            value={config.model_name}
            onChange={(e) => setConfig({...config, model_name: e.target.value})}
            placeholder="google/gemini-flash-1.5"
            className="input-field"
          />
          <p className="text-xs text-gray-500 mt-1">
            Recommended: google/gemini-flash-1.5, openai/gpt-3.5-turbo, anthropic/claude-3-haiku
          </p>
        </div>

        {/* Number of Pages */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Pages to Extract: {config.num_pages}
          </label>
          <input
            type="range"
            min="1"
            max="10"
            value={config.num_pages}
            onChange={(e) => setConfig({...config, num_pages: parseInt(e.target.value)})}
            className="w-full"
          />
          <div className="flex justify-between text-xs text-gray-500">
            <span>1</span>
            <span>10</span>
          </div>
        </div>

        {/* Number of Tags */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Tags to Generate: {config.num_tags}
          </label>
          <input
            type="range"
            min="3"
            max="15"
            value={config.num_tags}
            onChange={(e) => setConfig({...config, num_tags: parseInt(e.target.value)})}
            className="w-full"
          />
          <div className="flex justify-between text-xs text-gray-500">
            <span>3</span>
            <span>15</span>
          </div>
        </div>
      </div>

      {/* Status */}
      <div className={`p-3 rounded text-sm ${
        config.api_key && config.model_name
          ? 'bg-green-50 text-green-700' 
          : 'bg-yellow-50 text-yellow-700'
      }`}>
        {config.api_key && config.model_name ? '✓ Ready' : '⚠ API key & model required'}
      </div>
    </div>
  )
}
