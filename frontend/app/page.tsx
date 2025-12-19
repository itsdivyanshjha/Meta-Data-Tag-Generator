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
    model_name: 'openai/gpt-4o-mini',
    num_pages: 3,
    num_tags: 8,
  })

  return (
    <div className="space-y-8">
      {/* Hero Section */}
      <div className="text-center space-y-4 py-6">
        <h2 className="text-4xl font-bold bg-gradient-to-r from-slate-900 via-sky-800 to-indigo-900 dark:from-white dark:via-sky-200 dark:to-indigo-200 bg-clip-text text-transparent">
          Intelligent Document Tagging
        </h2>
        <p className="text-lg text-slate-600 dark:text-slate-300 max-w-2xl mx-auto">
          Upload your PDF documents and let AI generate relevant, searchable meta-tags instantly.
          Perfect for document management and organization.
        </p>
      </div>

      {/* Mode Selector */}
      <div className="flex justify-center">
        <div className="inline-flex p-1.5 rounded-2xl bg-slate-100 dark:bg-slate-800 shadow-inner">
          <button
            onClick={() => setMode('single')}
            className={`px-8 py-3 rounded-xl font-semibold transition-all duration-300 ${
              mode === 'single'
                ? 'bg-white dark:bg-slate-700 text-sky-600 dark:text-sky-400 shadow-lg'
                : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200'
            }`}
          >
            <span className="flex items-center gap-2">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              Single PDF
            </span>
          </button>
          <button
            onClick={() => setMode('batch')}
            className={`px-8 py-3 rounded-xl font-semibold transition-all duration-300 ${
              mode === 'batch'
                ? 'bg-white dark:bg-slate-700 text-sky-600 dark:text-sky-400 shadow-lg'
                : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200'
            }`}
          >
            <span className="flex items-center gap-2">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
              </svg>
              Batch CSV
            </span>
          </button>
        </div>
      </div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Config Panel - Left Side */}
        <div className="lg:col-span-1 order-2 lg:order-1">
          <ConfigPanel config={config} setConfig={setConfig} />
        </div>

        {/* Upload Area - Right Side */}
        <div className="lg:col-span-2 order-1 lg:order-2">
          {mode === 'single' ? (
            <SingleUpload config={config} />
          ) : (
            <BatchUpload config={config} />
          )}
        </div>
      </div>

      {/* Features Section */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-8">
        <div className="glass-card p-6 text-center">
          <div className="w-12 h-12 mx-auto mb-4 rounded-xl bg-gradient-to-br from-sky-500 to-sky-600 flex items-center justify-center">
            <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
          <h3 className="font-semibold text-slate-800 dark:text-slate-200 mb-2">Lightning Fast</h3>
          <p className="text-sm text-slate-600 dark:text-slate-400">Process documents in seconds with powerful AI models</p>
        </div>
        
        <div className="glass-card p-6 text-center">
          <div className="w-12 h-12 mx-auto mb-4 rounded-xl bg-gradient-to-br from-indigo-500 to-indigo-600 flex items-center justify-center">
            <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            </svg>
          </div>
          <h3 className="font-semibold text-slate-800 dark:text-slate-200 mb-2">Secure Processing</h3>
          <p className="text-sm text-slate-600 dark:text-slate-400">Your API key stays in your browser. Documents are processed securely.</p>
        </div>
        
        <div className="glass-card p-6 text-center">
          <div className="w-12 h-12 mx-auto mb-4 rounded-xl bg-gradient-to-br from-purple-500 to-purple-600 flex items-center justify-center">
            <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
            </svg>
          </div>
          <h3 className="font-semibold text-slate-800 dark:text-slate-200 mb-2">Batch Processing</h3>
          <p className="text-sm text-slate-600 dark:text-slate-400">Process multiple documents at once with CSV upload</p>
        </div>
      </div>
    </div>
  )
}

