import { FileText } from 'lucide-react'
import { EmptyState } from '@/components/common/EmptyState'

export const DocumentsView = () => {
  return (
    <EmptyState
      icon={FileText}
      title="Document Ingestion & Web Scraping Pipeline"
      description="Semantic web content extraction via Crawl4AI and high-fidelity PDF, DOCX, and XLSX table extraction with bounding box provenance via IBM Docling."
      scheduledBrick="BRICK-007: Crawl4AI & Docling Pipeline"
      stage="Stage 4: Browser Automation & Web Intelligence"
      prerequisites={[
        'BRICK-007: Crawl4AI Semantic Markdown Extraction',
        'BRICK-007: Docling TableFormer Model & Provenance Metadata',
      ]}
      architectureNote="Architecture Reference: ADR-006 & Section 3.7 of docs/ARCHITECTURE.md."
    />
  )
}
