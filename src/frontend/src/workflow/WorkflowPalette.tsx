import React, {useState, useMemo} from 'react';
import {PALETTE_CATEGORIES, PALETTE_ITEMS, type ComponentPaletteItem, type StudioNodeCategory} from './workflowTypes';

interface WorkflowPaletteProps {
  onAddNode?: (item: ComponentPaletteItem) => void;
}

export function WorkflowPalette({onAddNode}: WorkflowPaletteProps) {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<StudioNodeCategory | 'all'>('all');

  const filteredItems = useMemo(() => {
    return PALETTE_ITEMS.filter((item) => {
      const matchSearch =
        item.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        item.description.toLowerCase().includes(searchTerm.toLowerCase());
      const matchCat = selectedCategory === 'all' || item.category === selectedCategory;
      return matchSearch && matchCat;
    });
  }, [searchTerm, selectedCategory]);

  const onDragStart = (event: React.DragEvent, item: ComponentPaletteItem) => {
    event.dataTransfer.setData('application/reactflow', JSON.stringify(item));
    event.dataTransfer.effectAllowed = 'move';
  };

  return (
    <aside className="workflow-palette" aria-label="컴포넌트 라이브러리">
      <div className="workflow-palette-header">
        <h3>
          <span>🧩</span> 컴포넌트 라이브러리
        </h3>
        <input
          type="text"
          className="workflow-palette-search"
          aria-label="컴포넌트 검색"
          placeholder="컴포넌트 검색..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
        />
        <div className="workflow-palette-filters" aria-label="컴포넌트 분류">
          <button
            type="button"
            className="workflow-btn-secondary"
            style={{
              padding: '2px 8px',
              fontSize: 11,
              borderRadius: 12,
              background: selectedCategory === 'all' ? '#4F46E5' : '#F1F5F9',
              color: selectedCategory === 'all' ? '#FFFFFF' : '#475569',
              border: 'none',
              cursor: 'pointer'
            }}
            onClick={() => setSelectedCategory('all')}
          >
            전체
          </button>
          {PALETTE_CATEGORIES.map((cat) => (
            <button
              key={cat.id}
              type="button"
              className="workflow-btn-secondary"
              style={{
                padding: '2px 8px',
                fontSize: 11,
                borderRadius: 12,
                background: selectedCategory === cat.id ? '#4F46E5' : '#F1F5F9',
                color: selectedCategory === cat.id ? '#FFFFFF' : '#475569',
                border: 'none',
                cursor: 'pointer',
                whiteSpace: 'nowrap'
              }}
              onClick={() => setSelectedCategory(cat.id)}
            >
              {cat.icon} {cat.label.split(' ')[0]}
            </button>
          ))}
        </div>
      </div>

      <div className="workflow-palette-list">
        <div style={{fontSize: 11, color: '#64748B', padding: '0 2px'}}>
          💡 캔버스로 노드를 <strong>드래그 &amp; 드롭</strong>하거나 클릭하여 추가하세요.
        </div>

        {PALETTE_CATEGORIES.map((category) => {
          const items = filteredItems.filter((i) => i.category === category.id);
          if (items.length === 0) return null;

          return (
            <div key={category.id} className="workflow-palette-category">
              <div className="workflow-palette-category-title">
                <span>{category.icon}</span> {category.label} ({items.length})
              </div>
              {items.map((item) => (
                <div
                  key={item.type}
                  className="workflow-palette-item"
                  draggable
                  onDragStart={(e) => onDragStart(e, item)}
                  onClick={() => onAddNode?.(item)}
                  title="클릭하거나 캔버스로 드래그하세요"
                >
                  <div className="workflow-palette-item-icon">{item.icon}</div>
                  <div className="workflow-palette-item-info">
                    <span className="workflow-palette-item-name">{item.name}</span>
                    <span className="workflow-palette-item-desc">{item.description}</span>
                  </div>
                </div>
              ))}
            </div>
          );
        })}

        {filteredItems.length === 0 && (
          <div style={{textAlign: 'center', padding: '30px 10px', color: '#94A3B8', fontSize: 13}}>
            검색 조건에 맞는 컴포넌트가 없습니다.
          </div>
        )}
      </div>
    </aside>
  );
}
