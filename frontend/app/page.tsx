'use client'

import { useState } from 'react'
import Link from 'next/link'
import SingleUpload from '@/components/SingleUpload'
import BatchUpload from '@/components/BatchUpload'
import ConfigPanel from '@/components/ConfigPanel'
import { TaggingConfig, ProcessingMode } from '@/lib/types'

export default function Home() {
  const [mode, setMode] = useState<ProcessingMode>('single')
  const [config, setConfig] = useState<TaggingConfig>({
    api_key: '',
    model_name: '',  // No default model - user must specify
    num_pages: 3,
    num_tags: 8,
  })
  const [exclusionFile, setExclusionFile] = useState<File | null>(null)

  return (
    <div className="flex flex-col" style={{ height: 'calc(100vh - 180px)' }}>
      {/* Toolbar with Mode Selector */}
      <div className="flex items-center justify-between mb-6 pb-4 border-b border-gray-200">
        <div className="flex gap-2">
          <button
            onClick={() => setMode('single')}
            className={`px-6 py-2 rounded-lg font-medium transition-all duration-200 ${
              mode === 'single'
                ? 'bg-gradient-to-r from-blue-600 to-blue-700 text-white shadow-md'
                : 'bg-white text-gray-700 border border-gray-300 hover:border-gray-400 hover:bg-gray-50'
            }`}
          >
            Single Document
          </button>
          <button
            onClick={() => setMode('batch')}
            className={`px-6 py-2 rounded-lg font-medium transition-all duration-200 ${
              mode === 'batch'
                ? 'bg-gradient-to-r from-blue-600 to-blue-700 text-white shadow-md'
                : 'bg-white text-gray-700 border border-gray-300 hover:border-gray-400 hover:bg-gray-50'
            }`}
          >
            Batch Processing
          </button>
        </div>

        {/* Reserved space for future profile section */}
        <div className="flex items-center gap-3">
          {/* Profile section will go here after auth implementation */}
        </div>
      </div>

      {/* Main Content - Takes remaining vertical space */}
      {mode === 'batch' ? (
        <div className="flex gap-8 flex-1 min-h-0">
          {/* Configuration Panel - Wider for better usability */}
          <div className="w-96 flex-shrink-0">
            <ConfigPanel
              config={config}
              setConfig={setConfig}
              onExclusionFileChange={setExclusionFile}
            />
          </div>
          {/* Batch Upload - Takes remaining space */}
          <div className="flex-1 min-w-0">
            <BatchUpload config={config} exclusionFile={exclusionFile} />
          </div>
        </div>
      ) : (
        <div className="flex gap-8 flex-1 min-h-0">
          {/* Configuration Panel - Wider sidebar */}
          <div className="w-96 flex-shrink-0">
            <ConfigPanel
              config={config}
              setConfig={setConfig}
              onExclusionFileChange={setExclusionFile}
            />
          </div>
          {/* Single Upload - Takes remaining space */}
          <div className="flex-1 min-w-0">
            <SingleUpload config={config} exclusionFile={exclusionFile} />
          </div>
        </div>
      )}
    </div>
  )
}
