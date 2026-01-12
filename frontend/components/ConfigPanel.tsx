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
    <div className="card p-8 h-full flex flex-col">
      <div className="flex-shrink-0 mb-8 pb-5 border-b border-gray-100">
        <h2 className="text-xl font-bold text-gray-900">Configuration</h2>
        <p className="text-sm text-gray-500 mt-1">Set up your processing parameters</p>
      </div>

      <div className="flex-1 overflow-y-auto space-y-6">
        {/* API Key */}
        <div>
          <label className="block text-sm font-semibold text-gray-900 mb-2">
            OpenRouter API Key
          </label>
          <input
            type="password"
            value={config.api_key}
            onChange={(e) => setConfig({...config, api_key: e.target.value})}
            placeholder="sk-or-v1-..."
            className="input-field"
          />
          <p className="text-xs text-gray-600 mt-2">
            Get your key at{' '}
            <a
              href="https://openrouter.ai/keys"
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-600 hover:text-blue-700 font-medium underline"
            >
              openrouter.ai/keys
            </a>
          </p>
        </div>

        {/* Model Name */}
        <div>
          <label className="block text-sm font-semibold text-gray-900 mb-2">
            Model Name
          </label>
          <input
            type="text"
            value={config.model_name}
            onChange={(e) => setConfig({...config, model_name: e.target.value})}
            placeholder="google/gemini-flash-1.5"
            className="input-field"
          />
          <p className="text-xs text-gray-600 mt-2">
            <span className="font-medium">Recommended:</span> google/gemini-flash-1.5, openai/gpt-3.5-turbo
          </p>
        </div>

        {/* Number of Pages */}
        <div>
          <label className="block text-sm font-semibold text-gray-900 mb-3">
            Pages to Extract: <span className="text-blue-600">{config.num_pages}</span>
          </label>
          <input
            type="range"
            min="1"
            max="10"
            value={config.num_pages}
            onChange={(e) => setConfig({...config, num_pages: parseInt(e.target.value)})}
            className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-600"
          />
          <div className="flex justify-between text-xs text-gray-500 mt-1">
            <span>1 page</span>
            <span>10 pages</span>
          </div>
        </div>

        {/* Number of Tags */}
        <div>
          <label className="block text-sm font-semibold text-gray-900 mb-3">
            Tags to Generate: <span className="text-blue-600">{config.num_tags}</span>
          </label>
          <input
            type="range"
            min="3"
            max="15"
            value={config.num_tags}
            onChange={(e) => setConfig({...config, num_tags: parseInt(e.target.value)})}
            className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-600"
          />
          <div className="flex justify-between text-xs text-gray-500 mt-1">
            <span>3 tags</span>
            <span>15 tags</span>
          </div>
        </div>

        {/* Exclusion List Upload */}
        <div>
          <label className="block text-sm font-semibold text-gray-900 mb-2">
            Exclusion List <span className="text-gray-500 font-normal">(Optional)</span>
          </label>
          <input
            type="file"
            accept=".txt,.pdf"
            onChange={handleExclusionFileUpload}
            className="input-field text-sm cursor-pointer"
          />
          <p className="text-xs text-gray-600 mt-2">
            Upload .txt or .pdf with words to exclude (one per line or comma-separated)
          </p>

          {exclusionFile && (
            <div className="mt-3 p-4 bg-gradient-to-r from-blue-50 to-indigo-50 rounded-lg border border-blue-200">
              <div className="flex items-start gap-3">
                <div className="flex-shrink-0 w-8 h-8 bg-blue-500 rounded-lg flex items-center justify-center">
                  <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-blue-900 truncate">
                    {exclusionFile.name}
                  </p>
                  <p className="text-xs text-blue-600 mt-0.5">
                    {(exclusionFile.size / 1024).toFixed(1)} KB
                  </p>
                </div>
              </div>

              {exclusionPreview.length > 0 && (
                <div className="mt-3 pt-3 border-t border-blue-300">
                  <p className="text-xs font-semibold text-blue-900 mb-1.5">Preview:</p>
                  <p className="text-xs text-blue-700 leading-relaxed">
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
      <div className={`p-5 rounded-xl text-sm flex-shrink-0 mt-6 border ${
        config.api_key && config.model_name
          ? 'bg-gradient-to-r from-green-50 to-emerald-50 border-green-200'
          : 'bg-gradient-to-r from-yellow-50 to-amber-50 border-yellow-200'
      }`}>
        <div className="flex items-center gap-2">
          {config.api_key && config.model_name ? (
            <>
              <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
              <span className="font-semibold text-green-900">Ready to process</span>
            </>
          ) : (
            <>
              <div className="w-2 h-2 bg-yellow-500 rounded-full"></div>
              <span className="font-semibold text-yellow-900">API key & model required</span>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
