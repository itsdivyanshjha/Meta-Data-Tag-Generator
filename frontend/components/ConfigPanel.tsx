'use client'

import { TaggingConfig } from '@/lib/types'
import { useState } from 'react'

interface ConfigPanelProps {
  config: TaggingConfig
  setConfig: (config: TaggingConfig) => void
  onExclusionFileChange?: (file: File | null) => void
}

export default function ConfigPanel({ config, setConfig, onExclusionFileChange }: ConfigPanelProps) {
  const [exclusionFile, setExclusionFile] = useState<File | null>(null)
  const [exclusionPreview, setExclusionPreview] = useState<string[]>([])

  const handleExclusionFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) {
      setExclusionFile(null)
      setExclusionPreview([])
      setConfig({...config, exclusion_words: undefined})
      if (onExclusionFileChange) {
        onExclusionFileChange(null)
      }
      return
    }

    setExclusionFile(file)
    if (onExclusionFileChange) {
      onExclusionFileChange(file)
    }

    // Preview first few words for .txt files
    if (file.name.endsWith('.txt')) {
      try {
        const text = await file.text()
        const words = text
          .split(/[\n,]/)
          .map(w => w.trim())
          .filter(w => w && !w.startsWith('#'))
        setExclusionPreview(words.slice(0, 10))
        setConfig({...config, exclusion_words: words})
      } catch (error) {
        console.error('Failed to read exclusion file:', error)
      }
    } else if (file.name.endsWith('.pdf')) {
      // For PDFs, we can't preview on frontend, but we'll send to backend
      setExclusionPreview([])
      setConfig({...config, exclusion_words: []})
    }
  }

  return (
    <div className="card p-5 h-full flex flex-col">
      <h2 className="text-lg font-bold text-gray-900 flex-shrink-0 mb-5">Configuration</h2>
      
      <div className="flex-1 overflow-y-auto space-y-4">
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

        {/* Exclusion List Upload */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Exclusion List (Optional)
          </label>
          <input
            type="file"
            accept=".txt,.pdf"
            onChange={handleExclusionFileUpload}
            className="input-field text-sm"
          />
          <p className="text-xs text-gray-500 mt-1">
            Upload a .txt or .pdf file with common words to exclude from tags (one per line or comma-separated)
          </p>
          
          {exclusionFile && (
            <div className="mt-2 p-3 bg-blue-50 rounded border border-blue-200">
              <div className="flex items-start gap-2">
                <span className="text-blue-600 text-sm">📄</span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-blue-900 truncate">
                    {exclusionFile.name}
                  </p>
                  <p className="text-xs text-blue-600 mt-0.5">
                    {(exclusionFile.size / 1024).toFixed(1)} KB
                  </p>
                </div>
              </div>
              
              {exclusionPreview.length > 0 && (
                <div className="mt-2 pt-2 border-t border-blue-200">
                  <p className="text-xs font-medium text-blue-900 mb-1">Preview:</p>
                  <p className="text-xs text-blue-700">
                    {exclusionPreview.join(', ')}
                    {config.exclusion_words && config.exclusion_words.length > 10 && 
                      ` ... and ${config.exclusion_words.length - 10} more`}
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Status */}
      <div className={`p-3 rounded text-sm flex-shrink-0 ${
        config.api_key && config.model_name
          ? 'bg-green-50 text-green-700' 
          : 'bg-yellow-50 text-yellow-700'
      }`}>
        {config.api_key && config.model_name ? '✓ Ready' : '⚠ API key & model required'}
      </div>
    </div>
  )
}
