'use client'

import { useState } from 'react'
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
    <div className="space-y-6">
      {/* Mode Selector */}
      <div className="flex justify-center gap-4">
        <button
          onClick={() => setMode('single')}
          className={`px-6 py-2 rounded font-medium ${
            mode === 'single'
              ? 'bg-blue-600 text-white'
              : 'bg-gray-200 text-gray-700'
          }`}
        >
          Single PDF
        </button>
        <button
          onClick={() => setMode('batch')}
          className={`px-6 py-2 rounded font-medium ${
            mode === 'batch'
              ? 'bg-blue-600 text-white'
              : 'bg-gray-200 text-gray-700'
          }`}
        >
          Batch CSV
        </button>
      </div>

      {/* Main Content */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1">
          <ConfigPanel 
            config={config} 
            setConfig={setConfig}
            onExclusionFileChange={setExclusionFile}
          />
        </div>
        <div className="lg:col-span-2">
          {mode === 'single' ? (
            <SingleUpload config={config} exclusionFile={exclusionFile} />
          ) : (
            <BatchUpload config={config} exclusionFile={exclusionFile} />
          )}
        </div>
      </div>
    </div>
  )
}
