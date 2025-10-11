import React, { useState, useRef, useCallback, useEffect, forwardRef, useImperativeHandle } from 'react';
import {
  Bold, Italic, Underline, AlignLeft, AlignCenter, AlignRight,
  Link, Image, List, ListOrdered, Quote, Code, Palette,
  Type, Paperclip, Eye, Send, Save, Upload, X, Plus,
  ChevronDown, Monitor, Smartphone, Tablet, Move, Copy,
  Grid, Square, Type as TextIcon, Mail, Calendar, User,
  Settings, Download, Upload as UploadIcon, Trash2,
  MousePointer, Edit3, Layout, AlertTriangle, CheckCircle,
  Shield, Zap, Users, GripVertical
} from 'lucide-react';

const EmailEditor = forwardRef((props, ref) => {
  // ==========================================
  // 📊 STATE MANAGEMENT
  // ==========================================
  const [content, setContent] = useState('');
  const [htmlContent, setHtmlContent] = useState('');
  const [previewMode, setPreviewMode] = useState('desktop');
  const [showPreview, setShowPreview] = useState(false);
  const [editMode, setEditMode] = useState('visual'); // 'visual', 'html', 'drag-drop'
  const [draggedElement, setDraggedElement] = useState(null);
  const [selectedElement, setSelectedElement] = useState(null);
  const [fontSize, setFontSize] = useState('14');
  const [fontFamily, setFontFamily] = useState('Arial');
  const [textColor, setTextColor] = useState('#000000');
  const [backgroundColor, setBackgroundColor] = useState('#ffffff');
  const [emailBlocks, setEmailBlocks] = useState([]);

  // ==========================================
  // 🚀 ENHANCED DRAG & DROP STATE
  // ==========================================
  const [isDragging, setIsDragging] = useState(false);
  const [dragHistory, setDragHistory] = useState([]);
  const [dragOverIndex, setDragOverIndex] = useState(null);
  const [touchStart, setTouchStart] = useState(null);
  const [gridSize] = useState(20); // Snap-to-grid size

  // ==========================================
  // 📊 DELIVERABILITY FEATURES
  // ==========================================
  const [deliverabilityScore, setDeliverabilityScore] = useState(100);
  const [spamWarnings, setSpamWarnings] = useState([]);
  const [imageTextWarning, setImageTextWarning] = useState(null);
  const [compatibilityWarnings, setCompatibilityWarnings] = useState([]);
  const [accessibilityWarnings, setAccessibilityWarnings] = useState([]);
  const [showDeliverabilityPanel, setShowDeliverabilityPanel] = useState(true);

  const editorRef = useRef(null);
  const htmlEditorRef = useRef(null);

  // ==========================================
  // 📝 SPAM WORDS DATABASE
  // ==========================================
  const spamTriggerWords = [
    'free', 'guarantee', 'limited time', 'urgent', 'click here', 'buy now',
    'offer', 'deal', 'discount', 'winner', 'congratulations', 'cash',
    'money', 'earn', 'income', 'opportunity', 'risk-free', 'no obligation',
    'act now', 'don\'t delay', 'instant', 'immediately', 'order now',
    'limited offer', 'exclusive', 'special promotion', 'clearance',
    'save up to', 'percent off', 'lowest price'
  ];

  // ==========================================
  // 🎨 PERSONALIZATION TAGS
  // ==========================================
  const personalizationTags = [
    { tag: '{{first_name}}', description: 'Subscriber first name' },
    { tag: '{{last_name}}', description: 'Subscriber last name' },
    { tag: '{{company}}', description: 'Company name' },
    { tag: '{{email}}', description: 'Email address' },
    { tag: '{{custom_field_1}}', description: 'Custom field 1' },
    { tag: '{{unsubscribe_url}}', description: 'Unsubscribe link' }
  ];

  // ==========================================
  // 🧱 EMAIL BLOCK TYPES (SINGLE IMAGE TYPE)
  // ==========================================
  const emailBlockTypes = [
    {
      id: 'text',
      name: 'Text Block',
      icon: TextIcon,
      defaultContent: '<p>Click to edit text...</p>',
      category: 'content'
    },
    {
      id: 'image',
      name: 'Image',
      icon: Image,
      defaultContent: `<img
        src="https://via.placeholder.com/600x400/e5e7eb/9ca3af?text=Click+to+Upload+Image"
        alt="Click to upload your image"
        width="600"
        height="400"
        style="width:100%; height:auto; display:block; margin:0 auto; border: 2px dashed #d1d5db; border-radius: 8px; cursor: pointer;"
      >`,
      category: 'media'
    },
    {
      id: 'button',
      name: 'Button',
      icon: Square,
      defaultContent: '<table style="margin: 0 auto;"><tr><td style="background-color:#007bff;padding:12px 24px;border-radius:4px;text-align:center;"><a href="#" style="color:#ffffff;text-decoration:none;font-weight:bold;display:block;">Click Me</a></td></tr></table>',
      category: 'interactive'
    },
    {
      id: 'divider',
      name: 'Divider',
      icon: Grid,
      defaultContent: '<hr style="border: none; border-top: 2px solid #eee; margin: 20px 0;">',
      category: 'layout'
    },
    {
      id: 'spacer',
      name: 'Spacer',
      icon: Square,
      defaultContent: '<div style="height: 30px;"></div>',
      category: 'layout'
    },
    {
      id: 'columns',
      name: '2 Columns',
      icon: Layout,
      defaultContent: '<table width="100%"><tr><td width="50%" style="padding:10px;"><p>Left column</p></td><td width="50%" style="padding:10px;"><p>Right column</p></td></tr></table>',
      category: 'layout'
    },
    {
      id: 'header',
      name: 'Header',
      icon: Type,
      defaultContent: '<h1 style="color: #333; font-size: 24px; margin: 0 0 16px 0;">Your Header Here</h1>',
      category: 'content'
    },
    {
      id: 'unsubscribe',
      name: 'Unsubscribe Link',
      icon: Link,
      defaultContent: '<p style="text-align:center;font-size:12px;color:#999;"><a href="{{unsubscribe_url}}" style="color:#999;">Unsubscribe</a> | <a href="#" style="color:#999;">Update Preferences</a></p>',
      category: 'compliance'
    }
  ];

  // ==========================================
  // 🎯 ENHANCED DRAG & DROP HANDLERS
  // ==========================================

  /**
   * Handles the start of a drag operation
   * @param {Event} e - Drag event
   * @param {Object} blockType - Block type being dragged
   * @param {number} index - Index if dragging existing block
   */
  const handleDragStart = (e, blockType, index = null) => {
    setDraggedElement(blockType);
    setIsDragging(true);

    // Save current state for undo functionality
    if (index !== null) {
      setDragHistory(prev => [...prev, {
        blockId: emailBlocks[index]?.id,
        oldPosition: index,
        oldBlocks: [...emailBlocks],
        timestamp: Date.now()
      }]);
    }

    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', JSON.stringify({
      type: blockType.id || blockType,
      index,
      isExisting: index !== null
    }));

    // Add visual drag feedback
    if (e.target) {
      e.target.style.opacity = '0.5';
      e.target.style.transform = 'rotate(2deg) scale(1.02)';
      e.target.style.boxShadow = '0 8px 25px rgba(0, 0, 0, 0.15)';
      e.target.style.zIndex = '1000';
    }
  };

  /**
   * Handles the end of a drag operation
   */
  const handleDragEnd = (e) => {
    setIsDragging(false);
    setDraggedElement(null);
    setDragOverIndex(null);

    // Reset drag styling
    if (e.target) {
      e.target.style.opacity = '1';
      e.target.style.transform = 'none';
      e.target.style.boxShadow = 'none';
      e.target.style.zIndex = 'auto';
    }
  };

  /**
   * Handles drag over events with snap-to-grid
   */
  const handleDragOver = (e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';

    // Visual feedback for drop zone
    e.currentTarget.style.borderColor = '#3b82f6';
    e.currentTarget.style.backgroundColor = '#eff6ff';
  };

  const handleDragLeave = (e) => {
    e.currentTarget.style.borderColor = '';
    e.currentTarget.style.backgroundColor = '';
  };

  /**
   * Handles drop operations
   */
  const handleDrop = (e, targetIndex = null) => {
    e.preventDefault();
    handleDragLeave(e);

    if (draggedElement) {
      const dragData = JSON.parse(e.dataTransfer.getData('text/plain'));

      if (dragData.isExisting && dragData.index !== null) {
        // Moving existing block
        moveBlock(dragData.index, targetIndex || emailBlocks.length);
      } else {
        // Adding new block
        const newBlock = {
          id: Date.now() + Math.random(),
          type: draggedElement.id || draggedElement,
          content: draggedElement.defaultContent || `<p>New ${draggedElement.name || 'Block'}</p>`,
          styles: {},
          position: targetIndex || emailBlocks.length
        };

        const newBlocks = [...emailBlocks];
        if (targetIndex !== null) {
          newBlocks.splice(targetIndex, 0, newBlock);
        } else {
          newBlocks.push(newBlock);
        }
        setEmailBlocks(newBlocks);
      }

      setDraggedElement(null);
    }
  };

  // ==========================================
  // 🔄 BLOCK MANIPULATION FUNCTIONS
  // ==========================================

  /**
   * Moves a block from one position to another
   */
  const moveBlock = (fromIndex, toIndex) => {
    const newBlocks = [...emailBlocks];
    const [movedBlock] = newBlocks.splice(fromIndex, 1);
    newBlocks.splice(Math.min(toIndex, newBlocks.length), 0, movedBlock);
    setEmailBlocks(newBlocks);
  };

  /**
   * Duplicates a block at a given index
   */
  const duplicateBlock = (index) => {
    const blockToDuplicate = emailBlocks[index];
    const newBlock = {
      ...blockToDuplicate,
      id: Date.now() + Math.random(),
    };
    const newBlocks = [...emailBlocks];
    newBlocks.splice(index + 1, 0, newBlock);
    setEmailBlocks(newBlocks);
  };

  /**
   * Deletes a block at a given index
   */
  const deleteBlock = (index) => {
    setEmailBlocks(emailBlocks.filter((_, i) => i !== index));
    if (selectedElement === emailBlocks[index]?.id) {
      setSelectedElement(null);
    }
  };

  /**
   * Updates the content of a block
   */
  const updateBlockContent = (index, newContent) => {
    const newBlocks = [...emailBlocks];
    newBlocks[index].content = newContent;
    setEmailBlocks(newBlocks);
  };

  // ==========================================
  // ⌨️ KEYBOARD NAVIGATION
  // ==========================================

  /**
   * Handles keyboard navigation for accessibility
   */
  const handleKeyDown = (e, blockIndex) => {
    if (selectedElement !== emailBlocks[blockIndex]?.id) return;

    switch (e.key) {
      case 'ArrowUp':
        e.preventDefault();
        if (blockIndex > 0) {
          moveBlock(blockIndex, blockIndex - 1);
        }
        break;
      case 'ArrowDown':
        e.preventDefault();
        if (blockIndex < emailBlocks.length - 1) {
          moveBlock(blockIndex, blockIndex + 1);
        }
        break;
      case 'Delete':
      case 'Backspace':
        e.preventDefault();
        deleteBlock(blockIndex);
        break;
      case 'z':
        if (e.ctrlKey || e.metaKey) {
          e.preventDefault();
          handleUndo();
        }
        break;
      case 'Escape':
        setSelectedElement(null);
        break;
    }
  };

  // ==========================================
  // 📱 MOBILE TOUCH SUPPORT
  // ==========================================

  /**
   * Handle touch start for mobile drag and drop
   */
  const handleTouchStart = (e, blockIndex) => {
    e.preventDefault();
    const touch = e.touches[0];
    setTouchStart({
      x: touch.clientX,
      y: touch.clientY,
      blockIndex,
      startTime: Date.now()
    });
    setSelectedElement(emailBlocks[blockIndex]?.id);
  };

  const handleTouchMove = (e) => {
    if (!touchStart) return;
    e.preventDefault();

    const touch = e.touches[0];
    const deltaY = touch.clientY - touchStart.y;

    if (Math.abs(deltaY) > 10) {
      setIsDragging(true);
    }
  };

  const handleTouchEnd = (e) => {
    if (!touchStart) return;

    const touchDuration = Date.now() - touchStart.startTime;
    const touch = e.changedTouches[0];
    const deltaY = touch.clientY - touchStart.y;

    if (touchDuration > 500 && Math.abs(deltaY) > 30) {
      const direction = deltaY > 0 ? 1 : -1;
      const newIndex = Math.max(0, Math.min(emailBlocks.length - 1, touchStart.blockIndex + direction));
      if (newIndex !== touchStart.blockIndex) {
        moveBlock(touchStart.blockIndex, newIndex);
      }
    }

    setTouchStart(null);
    setIsDragging(false);
  };

  // ==========================================
  // 🔙 UNDO FUNCTIONALITY
  // ==========================================

  /**
   * Handles undo operations
   */
  const handleUndo = () => {
    const lastChange = dragHistory[dragHistory.length - 1];
    if (lastChange) {
      setEmailBlocks(lastChange.oldBlocks);
      setDragHistory(prev => prev.slice(0, -1));
    }
  };

  // ==========================================
  // 🎯 DELIVERABILITY ANALYSIS ENGINE
  // ==========================================

  /**
   * Analyzes email content for deliverability issues
   */
  const analyzeDeliverability = useCallback((html) => {
    let score = 100;
    const warnings = [];
    const compatibility = [];
    const accessibility = [];

    if (!html || html.trim() === '') return { score, warnings, compatibility, accessibility };

    // Spam word analysis
    const contentLower = html.toLowerCase();
    const detectedSpamWords = spamTriggerWords.filter(word => contentLower.includes(word));
    if (detectedSpamWords.length > 0) {
      const penalty = Math.min(detectedSpamWords.length * 8, 40);
      score -= penalty;
      warnings.push(`🚨 ${detectedSpamWords.length} spam trigger words detected: ${detectedSpamWords.join(', ')}`);
    }

    // Image-to-text ratio analysis
    const textContent = html.replace(/<[^>]*>/g, '').trim();
    const textLength = textContent.length;
    const imageCount = (html.match(/<img\b[^>]*>/gi) || []).length;

    if (imageCount > 0) {
      const ratio = textLength / imageCount;
      if (ratio < 100) {
        score -= 20;
        warnings.push(`📸 Poor image-to-text ratio (${Math.round(ratio)} chars per image). Aim for 100+ characters per image.`);
      }
    }

    if (imageCount > 5) {
      score -= 10;
      warnings.push(`📸 Too many images (${imageCount}). Consider reducing to 5 or fewer.`);
    }

    // Email client compatibility
    if (html.includes('flexbox') || html.includes('display: flex')) {
      compatibility.push('⚠️ Flexbox may not work in Outlook. Consider table-based layouts.');
    }

    if (html.includes('position: absolute') || html.includes('position: fixed')) {
      compatibility.push('⚠️ Absolute/fixed positioning not supported in most email clients.');
    }

    if (html.match(/<video|<audio/i)) {
      compatibility.push('⚠️ Video/audio elements not supported in most email clients.');
    }

    // Image dimension analysis
    const imageIssues = analyzeImageDimensions(html);
    if (imageIssues.length > 0) {
      compatibility.push(`📐 ${imageIssues.length} images missing proper dimensions. This may cause layout issues in Outlook.`);
      imageIssues.forEach(issue => {
        compatibility.push(`   • Image ${issue.index}: ${issue.problems.join(', ')}`);
      });
    }

    // Accessibility analysis
    const imgTagsForAlt = html.match(/<img[^>]*>/gi) || [];
    const imagesWithoutAlt = imgTagsForAlt.filter(img => !img.includes('alt='));
    if (imagesWithoutAlt.length > 0) {
      accessibility.push(`♿ ${imagesWithoutAlt.length} images missing alt text for screen readers.`);
      score -= 5;
    }

    const headings = html.match(/<h[1-6][^>]*>/gi) || [];
    if (headings.length === 0 && textLength > 200) {
      accessibility.push('♿ Consider adding headings to improve content structure.');
    }

    if (!contentLower.includes('unsubscribe')) {
      score -= 25;
      warnings.push('🚨 Missing unsubscribe link - required by law and improves deliverability.');
    }

    if (html.includes('"click here"') || html.includes('"here"')) {
      accessibility.push('♿ Avoid "click here" links. Use descriptive link text.');
    }

    return {
      score: Math.max(0, Math.round(score)),
      warnings,
      compatibility,
      accessibility
    };
  }, []);

  // ==========================================
  // 🖼️ IMAGE ANALYSIS FUNCTIONS
  // ==========================================

  /**
   * Analyzes image dimensions for email compatibility
   */
  const analyzeImageDimensions = (html) => {
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, 'text/html');
    const images = doc.querySelectorAll('img');
    const issues = [];

    images.forEach((img, index) => {
      const problems = [];

      const width = img.getAttribute('width');
      if (!width) {
        problems.push('missing width attribute');
      } else if (width === 'auto' || isNaN(width)) {
        problems.push('invalid width attribute (must be numeric)');
      }

      const height = img.getAttribute('height');
      if (!height) {
        problems.push('missing height attribute');
      } else if (height === 'auto' || isNaN(height)) {
        problems.push('invalid height attribute (must be numeric)');
      }

      if (!img.getAttribute('alt')) {
        problems.push('missing alt text');
      }

      const style = img.getAttribute('style') || '';
      if (!style.includes('width:') || !style.includes('height:')) {
        problems.push('missing responsive CSS');
      }

      if (problems.length > 0) {
        issues.push({
          index: index + 1,
          src: img.getAttribute('src') || 'Unknown source',
          problems: problems
        });
      }
    });

    return issues;
  };

  /**
   * Auto-fixes image dimension issues
   */
  const fixImageDimensions = () => {
    let currentHtml = '';

    if (editMode === 'html') {
      currentHtml = htmlContent;
    } else if (editMode === 'drag-drop') {
      currentHtml = emailBlocks.map(block => block.content).join('\n');
    } else {
      currentHtml = content;
    }

    const fixedHtml = currentHtml.replace(
      /<img([^>]*?)>/gi,
      (match, attributes) => {
        const srcMatch = attributes.match(/src=["']([^"']+)["']/);
        if (!srcMatch) return match;

        const src = srcMatch[1];
        let newAttributes = attributes;

        const dimensionMatch = src.match(/\/(\d+)x(\d+)[\/?]/);
        let originalWidth = dimensionMatch ? dimensionMatch[1] : '600';
        let originalHeight = dimensionMatch ? dimensionMatch[2] : '400';

        if (!attributes.includes('width=')) {
          newAttributes += ` width="${originalWidth}"`;
        } else {
          newAttributes = newAttributes.replace(/width=["']([^"']*?)["']/g, (match, value) => {
            return isNaN(value) ? `width="${originalWidth}"` : match;
          });
        }

        if (!attributes.includes('height=')) {
          newAttributes += ` height="${originalHeight}"`;
        } else {
          newAttributes = newAttributes.replace(/height=["']([^"']*?)["']/g, (match, value) => {
            return (value === 'auto' || isNaN(value)) ? `height="${originalHeight}"` : match;
          });
        }

        if (!attributes.includes('style=')) {
          newAttributes += ' style="width:100%; height:auto; display:block;"';
        } else {
          newAttributes = newAttributes.replace(/style=["']([^"']*?)["']/g, (match, styleContent) => {
            let styles = styleContent;
            if (!styles.includes('width:')) styles += ' width:100%;';
            if (!styles.includes('height:')) styles += ' height:auto;';
            if (!styles.includes('display:')) styles += ' display:block;';
            return `style="${styles.trim()}"`;
          });
        }

        return `<img${newAttributes}>`;
      }
    );

    if (editMode === 'html') {
      setHtmlContent(fixedHtml);
    } else if (editMode === 'visual') {
      setContent(fixedHtml);
    } else if (editMode === 'drag-drop') {
      const parser = new DOMParser();
      const doc = parser.parseFromString(fixedHtml, 'text/html');
      const elements = Array.from(doc.body.children);
      const newBlocks = elements.map((el, index) => ({
        id: Date.now() + index,
        type: 'custom',
        content: el.outerHTML,
        styles: {},
        position: index
      }));
      setEmailBlocks(newBlocks);
    }

    alert('✅ All images have been fixed with proper HTML attributes and responsive CSS!');
  };

  // ==========================================
  // 🎨 PERSONALIZATION FUNCTIONS
  // ==========================================

  /**
   * Inserts personalization tags into the editor
   * Fixed to work properly across all editor modes
   */
  const insertPersonalizationTag = (tag) => {
    if (editMode === 'visual' && editorRef.current) {
      // Get current selection
      const selection = window.getSelection();
      if (selection.rangeCount > 0) {
        const range = selection.getRangeAt(0);
        range.deleteContents();

        // Create text node with the tag
        const textNode = document.createTextNode(tag);
        range.insertNode(textNode);

        // Move cursor after inserted tag
        range.setStartAfter(textNode);
        range.setEndAfter(textNode);
        selection.removeAllRanges();
        selection.addRange(range);
      } else {
        // If no selection, append to end
        editorRef.current.focus();
        document.execCommand('insertText', false, tag);
      }

      // Update content state
      setContent(editorRef.current.innerHTML);

    } else if (editMode === 'html' && htmlEditorRef.current) {
      const textarea = htmlEditorRef.current;
      const start = textarea.selectionStart;
      const end = textarea.selectionEnd;
      const newContent = htmlContent.substring(0, start) + tag + htmlContent.substring(end);
      setHtmlContent(newContent);

      // Move cursor after inserted tag
      setTimeout(() => {
        textarea.setSelectionRange(start + tag.length, start + tag.length);
        textarea.focus();
      }, 10);

    } else if (editMode === 'drag-drop') {
      // Insert into selected block or create new text block
      if (selectedElement) {
        const blockIndex = emailBlocks.findIndex(block => block.id === selectedElement);
        if (blockIndex !== -1) {
          const block = emailBlocks[blockIndex];
          const updatedContent = block.content + tag;
          updateBlockContent(blockIndex, updatedContent);
        }
      } else {
        // Create new text block with personalization tag
        const newBlock = {
          id: Date.now() + Math.random(),
          type: 'text',
          content: `<p>${tag}</p>`,
          styles: {},
          position: emailBlocks.length
        };
        setEmailBlocks([...emailBlocks, newBlock]);
      }
    }
  };

  // ==========================================
  // 🖼️ IMAGE UPLOAD FUNCTIONS
  // ==========================================

  /**
   * Enhanced image insertion with file upload support
   */
  const insertImage = () => {
    // Create file input element
    const fileInput = document.createElement('input');
    fileInput.type = 'file';
    fileInput.accept = 'image/*';
    fileInput.style.display = 'none';

    fileInput.onchange = function (e) {
      const file = e.target.files[0];
      if (file) {
        // Validate file size (max 5MB)
        if (file.size > 5 * 1024 * 1024) {
          alert('Image file size must be less than 5MB');
          return;
        }

        // Validate file type
        if (!file.type.startsWith('image/')) {
          alert('Please select a valid image file');
          return;
        }

        const reader = new FileReader();
        reader.onload = function (e) {
          const imageData = e.target.result;

          // Get image properties
          const img = new Image();
          img.onload = function () {
            const originalWidth = this.width;
            const originalHeight = this.height;

            // Prompt for alt text and dimensions
            const alt = prompt('Enter alt text (for accessibility):', file.name.replace(/\.[^/.]+$/, ""));
            const maxWidth = prompt('Enter max width (recommended: 400-600px):', '400');

            if (alt !== null && maxWidth !== null) {
              // Calculate proportional height
              const proportionalHeight = Math.round((originalHeight / originalWidth) * parseInt(maxWidth));

              const imgHtml = `<img
                src="${imageData}"
                alt="${alt || 'Uploaded image'}"
                width="${maxWidth}"
                height="${proportionalHeight}"
                style="max-width: 100%; height: auto; display: block; border: 0;"
              />`;

              if (editMode === 'visual' && editorRef.current) {
                formatText('insertHTML', imgHtml);
              } else if (editMode === 'html') {
                const textarea = htmlEditorRef.current;
                const start = textarea.selectionStart;
                const end = textarea.selectionEnd;
                const newContent = htmlContent.substring(0, start) + imgHtml + htmlContent.substring(end);
                setHtmlContent(newContent);
              }
            }
          };
          img.src = imageData;
        };
        reader.readAsDataURL(file);
      }

      // Cleanup
      document.body.removeChild(fileInput);
    };

    // Also support URL input as fallback
    const useUrl = confirm('Upload image file from computer?\nClick "Cancel" to use URL instead.');

    if (useUrl) {
      document.body.appendChild(fileInput);
      fileInput.click();
    } else {
      // Original URL-based approach
      const url = prompt('Enter image URL:');
      const alt = prompt('Enter alt text (for accessibility):');
      const width = prompt('Enter width (recommended: 400-600px):', '400');
      const height = prompt('Enter height (or leave blank for auto):', '');

      if (url) {
        const heightAttr = height ? `height="${height}"` : '';
        const heightStyle = height ? `height: ${height}px;` : 'height: auto;';

        const imgHtml = `<img
          src="${url}"
          alt="${alt || 'Image'}"
          width="${width}"
          ${heightAttr}
          style="max-width: 100%; ${heightStyle} display: block; border: 0;"
        />`;

        formatText('insertHTML', imgHtml);
      }
    }
  };

  // ==========================================
  // 📝 TEXT FORMATTING FUNCTIONS
  // ==========================================

  const formatText = (command, value = null) => {
    document.execCommand(command, false, value);
    editorRef.current?.focus();
  };

  const insertLink = () => {
    const url = prompt('Enter URL:');
    if (url) {
      formatText('createLink', url);
    }
  };

  const changeTextColor = (color) => {
    setTextColor(color);
    formatText('foreColor', color);
  };

  const changeBackgroundColor = (color) => {
    setBackgroundColor(color);
    formatText('backColor', color);
  };

  // ==========================================
  // 📊 REAL-TIME DELIVERABILITY MONITORING
  // ==========================================

  useEffect(() => {
    let currentHtml = '';

    if (editMode === 'html') {
      currentHtml = htmlContent;
    } else if (editMode === 'drag-drop') {
      currentHtml = emailBlocks.map(block => block.content).join('\n');
    } else {
      currentHtml = content;
    }

    const analysis = analyzeDeliverability(currentHtml);
    setDeliverabilityScore(analysis.score);
    setSpamWarnings(analysis.warnings);
    setCompatibilityWarnings(analysis.compatibility);
    setAccessibilityWarnings(analysis.accessibility);
  }, [content, htmlContent, emailBlocks, editMode, analyzeDeliverability]);

  // ==========================================
  // ⚙️ TEMPLATE MANAGEMENT FUNCTIONS
  // ==========================================

  const exportHTML = () => {
    let htmlToExport = '';
    if (editMode === 'drag-drop') {
      htmlToExport = emailBlocks.map(block => block.content).join('\n');
    } else if (editMode === 'html') {
      htmlToExport = htmlContent;
    } else {
      htmlToExport = content;
    }

    const fullHTML = `
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Email Template</title>
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; }
        .email-container { max-width: 600px; margin: 0 auto; }
        @media only screen and (max-width: 600px) {
          .mobile-full { width: 100% !important; }
          .mobile-hide { display: none !important; }
        }
    </style>
</head>
<body>
    <div class="email-container">
        ${htmlToExport}
    </div>
</body>
</html>`;

    const blob = new Blob([fullHTML], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'email-template.html';
    a.click();
    URL.revokeObjectURL(url);
  };

  // ==========================================
  // 🔄 CONTENT SYNCHRONIZATION
  // ==========================================

  useEffect(() => {
    if (editMode === 'html' && htmlEditorRef.current) {
      if (editMode === 'drag-drop') {
        const blocksHtml = emailBlocks.map(block => block.content).join('\n');
        setHtmlContent(blocksHtml);
      } else {
        setHtmlContent(content);
      }
    }
  }, [content, emailBlocks, editMode]);

  // ==========================================
  // ⚙️ IMPERATIVE HANDLE FOR COMPATIBILITY
  // ==========================================

  useImperativeHandle(ref, () => ({
    editor: {
      exportHtml: (callback) => {
        let finalContent = '';
        let design = {};

        if (editMode === 'html') {
          finalContent = htmlContent;
          design = { mode: 'html', content: htmlContent };
        } else if (editMode === 'drag-drop') {
          finalContent = emailBlocks.map(block => block.content).join('\n');
          design = { mode: 'drag-drop', blocks: emailBlocks };
        } else {
          finalContent = content;
          design = { mode: 'visual', content: content };
        }

        callback({
          design: design,
          html: finalContent
        });
      },

      loadDesign: (design) => {
  if (design && design.mode === 'html' && design.content) {
    setEditMode('html');
    setContent(design.content);     // ← ADD THIS LINE
    setHtmlContent(design.content);
  } else if (design && design.mode === 'drag-drop' && design.blocks) {
    setEditMode('drag-drop');
    setEmailBlocks(design.blocks);
  } else if (design && design.mode === 'visual' && design.content) {
    setEditMode('visual');
    setContent(design.content);
    setHtmlContent(design.content); // ← ADD THIS LINE for consistency
  } else if (design && design.body && design.body.rows) {
    let extractedHtml = '';
    try {
      design.body.rows.forEach(row => {
        row.columns?.forEach(column => {
          column.contents?.forEach(content => {
            if (content.type === 'html' && content.values?.html) {
              extractedHtml += content.values.html + '\n';
            }
          });
        });
      });
    } catch (e) {
      console.error('Error extracting HTML from old format:', e);
    }

    if (extractedHtml.trim()) {
      setEditMode('html');
      setContent(extractedHtml.trim());     // ← ADD THIS LINE
      setHtmlContent(extractedHtml.trim());
    } else {
      setEditMode('visual');
      setContent('');
      setHtmlContent('');  // ← ADD THIS LINE for consistency
    }
  } else if (design && design.html) {
    setEditMode('visual');
    setContent(design.html);
    setHtmlContent(design.html); // ← ADD THIS LINE for consistency
  } else {
    setEditMode('visual');
    setContent('');
    setHtmlContent(''); // ← ADD THIS LINE for consistency
  }
},


      loadBlank: () => {
        setContent('');
        setHtmlContent('');
        setEmailBlocks([]);
        setEditMode('visual');
      }
    }
  }));

  useEffect(() => {
    if (props.onLoad) {
      props.onLoad();
    }
  }, [props.onLoad]);

  // ==========================================
  // 🎯 COMPACT BUTTON SETTINGS FOR TOOLBAR
  // ==========================================

  /**
   * Button settings component - appears only in toolbar
   */
  const ButtonSettings = ({ block, index, updateBlockContent }) => {
    const [buttonText, setButtonText] = useState('Click Me');
    const [buttonColor, setButtonColor] = useState('#007bff');
    const [buttonUrl, setButtonUrl] = useState('#');
    const [buttonWidth, setButtonWidth] = useState('auto');
    const [paddingVertical, setPaddingVertical] = useState('12');
    const [paddingHorizontal, setPaddingHorizontal] = useState('24');
    const [borderRadius, setBorderRadius] = useState('4');
    const [textColor, setTextColor] = useState('#ffffff');
    const [alignment, setAlignment] = useState('center');

    // Extract current values from block content when component mounts
    useEffect(() => {
      if (block.content) {
        const parser = new DOMParser();
        const doc = parser.parseFromString(block.content, 'text/html');
        const link = doc.querySelector('a');
        const td = doc.querySelector('td');

        if (link) {
          setButtonText(link.textContent || 'Click Me');
          setButtonUrl(link.getAttribute('href') || '#');

          const linkStyle = link.getAttribute('style') || '';
          const colorMatch = linkStyle.match(/color:\s*([^;]+)/);
          if (colorMatch) setTextColor(colorMatch[1]);
        }

        if (td) {
          const style = td.getAttribute('style') || '';
          const bgMatch = style.match(/background-color:\s*([^;]+)/);
          if (bgMatch) setButtonColor(bgMatch[1]);

          const paddingMatch = style.match(/padding:\s*(\d+)px\s+(\d+)px/);
          if (paddingMatch) {
            setPaddingVertical(paddingMatch[1]);
            setPaddingHorizontal(paddingMatch[2]);
          }

          const radiusMatch = style.match(/border-radius:\s*(\d+)px/);
          if (radiusMatch) setBorderRadius(radiusMatch[1]);
        }
      }
    }, [block.content]);

    const updateButton = () => {
      const widthStyle = buttonWidth !== 'auto' ? `width: ${buttonWidth}px; min-width: ${buttonWidth}px;` : '';
      const alignmentStyle = alignment === 'center' ? 'margin: 0 auto;' :
        alignment === 'right' ? 'margin-left: auto; margin-right: 0;' :
          'margin-left: 0; margin-right: auto;';

      const newContent = `
        <table style="${alignmentStyle}" cellpadding="0" cellspacing="0">
          <tr>
            <td style="
              background-color: ${buttonColor};
              padding: ${paddingVertical}px ${paddingHorizontal}px;
              border-radius: ${borderRadius}px;
              ${widthStyle}
              text-align: center;
              vertical-align: middle;
            ">
              <a href="${buttonUrl}" style="
                color: ${textColor};
                text-decoration: none;
                font-weight: bold;
                display: block;
                line-height: 1.4;
              ">${buttonText}</a>
            </td>
          </tr>
        </table>`;
      updateBlockContent(index, newContent);
    };

    return (
      <div className="space-y-4">
        {/* Basic Settings */}
        <div className="grid grid-cols-4 gap-4">
          <div>
            <label className="block text-xs font-medium mb-1">Button Text</label>
            <input
              type="text"
              value={buttonText}
              onChange={(e) => setButtonText(e.target.value)}
              className="w-full px-2 py-1 border rounded text-sm"
              placeholder="Button text"
            />
          </div>

          <div>
            <label className="block text-xs font-medium mb-1">URL</label>
            <input
              type="url"
              value={buttonUrl}
              onChange={(e) => setButtonUrl(e.target.value)}
              className="w-full px-2 py-1 border rounded text-sm"
              placeholder="https://..."
            />
          </div>

          <div>
            <label className="block text-xs font-medium mb-1">Background Color</label>
            <input
              type="color"
              value={buttonColor}
              onChange={(e) => setButtonColor(e.target.value)}
              className="w-full h-8 border rounded cursor-pointer"
            />
          </div>

          <div>
            <label className="block text-xs font-medium mb-1">Text Color</label>
            <input
              type="color"
              value={textColor}
              onChange={(e) => setTextColor(e.target.value)}
              className="w-full h-8 border rounded cursor-pointer"
            />
          </div>
        </div>

        {/* Size and Alignment */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-medium mb-1">Width</label>
            <select
              value={buttonWidth}
              onChange={(e) => setButtonWidth(e.target.value)}
              className="w-full px-2 py-1 border rounded text-sm"
            >
              <option value="auto">Auto</option>
              <option value="120">120px</option>
              <option value="150">150px</option>
              <option value="200">200px</option>
              <option value="250">250px</option>
              <option value="300">300px</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium mb-1">Alignment</label>
            <select
              value={alignment}
              onChange={(e) => setAlignment(e.target.value)}
              className="w-full px-2 py-1 border rounded text-sm"
            >
              <option value="left">Left</option>
              <option value="center">Center</option>
              <option value="right">Right</option>
            </select>
          </div>
        </div>

        {/* Styling Controls - Sliders */}
        <div className="grid grid-cols-3 gap-4">
          <div>
            <label className="block text-xs font-medium mb-1">
              Vertical Padding: <span className="text-blue-600">{paddingVertical}px</span>
            </label>
            <input
              type="range"
              min="8" max="25"
              value={paddingVertical}
              onChange={(e) => setPaddingVertical(e.target.value)}
              className="w-full"
            />
          </div>

          <div>
            <label className="block text-xs font-medium mb-1">
              Horizontal Padding: <span className="text-blue-600">{paddingHorizontal}px</span>
            </label>
            <input
              type="range"
              min="15" max="50"
              value={paddingHorizontal}
              onChange={(e) => setPaddingHorizontal(e.target.value)}
              className="w-full"
            />
          </div>

          <div>
            <label className="block text-xs font-medium mb-1">
              Border Radius: <span className="text-blue-600">{borderRadius}px</span>
            </label>
            <input
              type="range"
              min="0" max="25"
              value={borderRadius}
              onChange={(e) => setBorderRadius(e.target.value)}
              className="w-full"
            />
          </div>
        </div>

        {/* Update Button */}
        <div className="pt-2 border-t">
          <button
            onClick={updateButton}
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 flex items-center gap-2"
          >
            <Settings size={16} />
            Update Button
          </button>
        </div>
      </div>
    );
  };

  // ==========================================
  // 🖼️ IMAGE SETTINGS FOR TOOLBAR
  // ==========================================

  /**
   * Image settings component with full editing capabilities
   */
  const ImageSettings = ({ block, index, updateBlockContent }) => {
    const [imageUrl, setImageUrl] = useState('');
    const [altText, setAltText] = useState('');
    const [imageWidth, setImageWidth] = useState('400');
    const [imageHeight, setImageHeight] = useState('auto');
    const [alignment, setAlignment] = useState('center');
    const [borderRadius, setBorderRadius] = useState('0');
    const [borderWidth, setBorderWidth] = useState('0');
    const [borderColor, setBorderColor] = useState('#cccccc');

    // Extract current values from block content
    useEffect(() => {
      if (block.content) {
        const parser = new DOMParser();
        const doc = parser.parseFromString(block.content, 'text/html');
        const img = doc.querySelector('img');

        if (img) {
          setImageUrl(img.getAttribute('src') || '');
          setAltText(img.getAttribute('alt') || '');
          setImageWidth(img.getAttribute('width') || '400');
          setImageHeight(img.getAttribute('height') || 'auto');

          const style = img.getAttribute('style') || '';
          const radiusMatch = style.match(/border-radius:\s*(\d+)px/);
          if (radiusMatch) setBorderRadius(radiusMatch[1]);

          const borderMatch = style.match(/border:\s*(\d+)px\s+solid\s+([^;]+)/);
          if (borderMatch) {
            setBorderWidth(borderMatch[1]);
            setBorderColor(borderMatch[2]);
          }

          if (style.includes('margin: 0 auto')) setAlignment('center');
          else if (style.includes('margin-left: auto')) setAlignment('right');
          else setAlignment('left');
        }
      }
    }, [block.content]);

    const handleFileUpload = () => {
      const fileInput = document.createElement('input');
      fileInput.type = 'file';
      fileInput.accept = 'image/*';
      fileInput.style.display = 'none';

      fileInput.onchange = function (e) {
        const file = e.target.files[0];
        if (file) {
          if (file.size > 5 * 1024 * 1024) {
            alert('Image must be less than 5MB');
            return;
          }

          const reader = new FileReader();
          reader.onload = function (e) {
            setImageUrl(e.target.result);
            setAltText(file.name.replace(/\.[^/.]+$/, ""));
          };
          reader.readAsDataURL(file);
        }
        document.body.removeChild(fileInput);
      };

      document.body.appendChild(fileInput);
      fileInput.click();
    };

    const updateImage = () => {
      const alignmentStyle = alignment === 'center' ? 'margin: 0 auto; display: block;' :
        alignment === 'right' ? 'margin-left: auto; display: block;' :
          'margin-right: auto; display: block;';

      const borderStyle = borderWidth > 0 ? `border: ${borderWidth}px solid ${borderColor};` : '';
      const radiusStyle = borderRadius > 0 ? `border-radius: ${borderRadius}px;` : '';

      const heightAttr = imageHeight !== 'auto' ? `height="${imageHeight}"` : '';
      const heightStyle = imageHeight !== 'auto' ? `height: ${imageHeight}px;` : 'height: auto;';

      const newContent = `<img
        src="${imageUrl}"
        alt="${altText}"
        width="${imageWidth}"
        ${heightAttr}
        style="max-width: 100%; ${heightStyle} ${alignmentStyle} ${borderStyle} ${radiusStyle}"
      />`;

      updateBlockContent(index, newContent);
    };

    return (
      <div className="space-y-4">
        {/* Image Source */}
        <div className="grid grid-cols-2 gap-4">
          <div className="col-span-2">
            <label className="block text-xs font-medium mb-2">Image Source</label>
            <div className="flex gap-2">
              <input
                type="url"
                value={imageUrl}
                onChange={(e) => setImageUrl(e.target.value)}
                className="flex-1 px-2 py-1 border rounded text-sm"
                placeholder="https://example.com/image.jpg"
              />
              <button
                onClick={handleFileUpload}
                className="px-3 py-1 bg-green-600 text-white rounded text-sm hover:bg-green-700 flex items-center gap-1"
              >
                <Upload size={14} />
                Upload
              </button>
            </div>
          </div>

          <div className="col-span-2">
            <label className="block text-xs font-medium mb-1">Alt Text (Accessibility)</label>
            <input
              type="text"
              value={altText}
              onChange={(e) => setAltText(e.target.value)}
              className="w-full px-2 py-1 border rounded text-sm"
              placeholder="Describe the image"
            />
          </div>
        </div>

        {/* Image Sizing */}
        <div className="grid grid-cols-3 gap-4">
          <div>
            <label className="block text-xs font-medium mb-1">Width (px)</label>
            <input
              type="number"
              value={imageWidth}
              onChange={(e) => setImageWidth(e.target.value)}
              className="w-full px-2 py-1 border rounded text-sm"
              min="50" max="800"
            />
          </div>

          <div>
            <label className="block text-xs font-medium mb-1">Height</label>
            <select
              value={imageHeight}
              onChange={(e) => setImageHeight(e.target.value)}
              className="w-full px-2 py-1 border rounded text-sm"
            >
              <option value="auto">Auto</option>
              <option value="200">200px</option>
              <option value="300">300px</option>
              <option value="400">400px</option>
              <option value="500">500px</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium mb-1">Alignment</label>
            <select
              value={alignment}
              onChange={(e) => setAlignment(e.target.value)}
              className="w-full px-2 py-1 border rounded text-sm"
            >
              <option value="left">Left</option>
              <option value="center">Center</option>
              <option value="right">Right</option>
            </select>
          </div>
        </div>

        {/* Styling Controls */}
        <div className="grid grid-cols-3 gap-4">
          <div>
            <label className="block text-xs font-medium mb-1">
              Border Width: <span className="text-blue-600">{borderWidth}px</span>
            </label>
            <input
              type="range"
              min="0" max="10"
              value={borderWidth}
              onChange={(e) => setBorderWidth(e.target.value)}
              className="w-full"
            />
          </div>

          <div>
            <label className="block text-xs font-medium mb-1">Border Color</label>
            <input
              type="color"
              value={borderColor}
              onChange={(e) => setBorderColor(e.target.value)}
              className="w-full h-8 border rounded cursor-pointer"
            />
          </div>

          <div>
            <label className="block text-xs font-medium mb-1">
              Border Radius: <span className="text-blue-600">{borderRadius}px</span>
            </label>
            <input
              type="range"
              min="0" max="50"
              value={borderRadius}
              onChange={(e) => setBorderRadius(e.target.value)}
              className="w-full"
            />
          </div>
        </div>

        {/* Update Button */}
        <div className="pt-2 border-t">
          <button
            onClick={updateImage}
            className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 flex items-center gap-2"
          >
            <Image size={16} />
            Update Image
          </button>
        </div>
      </div>
    );
  };

  // ==========================================
  // 📝 TEXT SETTINGS FOR TOOLBAR
  // ==========================================

  /**
   * Text settings component for basic text formatting
   */
  const TextSettings = ({ block, index, updateBlockContent }) => {
    const [textAlign, setTextAlign] = useState('left');
    const [fontSize, setFontSize] = useState('14');
    const [fontFamily, setFontFamily] = useState('Arial');
    const [textColor, setTextColor] = useState('#333333');
    const [lineHeight, setLineHeight] = useState('1.4');

    const updateText = () => {
      const parser = new DOMParser();
      const doc = parser.parseFromString(block.content, 'text/html');
      const element = doc.body.firstChild;

      if (element) {
        element.style.textAlign = textAlign;
        element.style.fontSize = fontSize + 'px';
        element.style.fontFamily = fontFamily;
        element.style.color = textColor;
        element.style.lineHeight = lineHeight;

        updateBlockContent(index, element.outerHTML);
      }
    };

    return (
      <div className="space-y-4">
        <div className="grid grid-cols-4 gap-4">
          <div>
            <label className="block text-xs font-medium mb-1">Font Family</label>
            <select
              value={fontFamily}
              onChange={(e) => setFontFamily(e.target.value)}
              className="w-full px-2 py-1 border rounded text-sm"
            >
              <option value="Arial">Arial</option>
              <option value="Georgia">Georgia</option>
              <option value="Times New Roman">Times New Roman</option>
              <option value="Helvetica">Helvetica</option>
              <option value="Verdana">Verdana</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium mb-1">Font Size</label>
            <select
              value={fontSize}
              onChange={(e) => setFontSize(e.target.value)}
              className="w-full px-2 py-1 border rounded text-sm"
            >
              <option value="12">12px</option>
              <option value="14">14px</option>
              <option value="16">16px</option>
              <option value="18">18px</option>
              <option value="20">20px</option>
              <option value="24">24px</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium mb-1">Text Color</label>
            <input
              type="color"
              value={textColor}
              onChange={(e) => setTextColor(e.target.value)}
              className="w-full h-8 border rounded cursor-pointer"
            />
          </div>

          <div>
            <label className="block text-xs font-medium mb-1">Alignment</label>
            <select
              value={textAlign}
              onChange={(e) => setTextAlign(e.target.value)}
              className="w-full px-2 py-1 border rounded text-sm"
            >
              <option value="left">Left</option>
              <option value="center">Center</option>
              <option value="right">Right</option>
              <option value="justify">Justify</option>
            </select>
          </div>
        </div>

        <div className="pt-2 border-t">
          <button
            onClick={updateText}
            className="px-4 py-2 bg-purple-600 text-white rounded hover:bg-purple-700 flex items-center gap-2"
          >
            <Type size={16} />
            Update Text
          </button>
        </div>
      </div>
    );
  };

  // ==========================================
  // 🎨 CLEAN PERSONALIZATION PANEL
  // ==========================================

  /**
   * Personalization panel without duplicate quick insert
   */
  const PersonalizationPanel = () => (
    <div className="mt-6">
      <h4 className="font-medium mb-3 flex items-center gap-2">
        <Zap size={16} />
        Personalization Tags
      </h4>
      <div className="space-y-2">
        {personalizationTags.map((tag, i) => (
          <button
            key={i}
            onClick={() => insertPersonalizationTag(tag.tag)}
            className="w-full text-left px-3 py-2 text-sm bg-blue-50 rounded hover:bg-blue-100 transition-colors border border-blue-200 flex justify-between items-center"
            title={tag.description}
          >
            <span className="font-mono text-blue-700">{tag.tag}</span>
            <span className="text-xs text-gray-600 truncate ml-2">{tag.description}</span>
          </button>
        ))}
      </div>
    </div>
  );

  // ==========================================
  // 🚀 SIMPLIFIED BLOCK ELEMENT (CLEAN CANVAS)
  // ==========================================

  /**
   * Block element with clean canvas - no inline settings
   */
  const BlockElement = ({ block, index }) => {
    const isSelected = selectedElement === block.id;
    const isButton = block.type === 'button';
    const isImage = block.type === 'image';

    return (
      <div
        key={block.id}
        className={`relative group border-2 border-dashed transition-all duration-200 p-3 mb-3 rounded-lg cursor-pointer ${isSelected ? 'border-blue-500 bg-blue-50 ring-2 ring-blue-200' :
            dragOverIndex === index ? 'border-green-500 bg-green-50' :
              'border-gray-300 hover:border-blue-400'
          }`}
        draggable={true}
        onDragStart={(e) => handleDragStart(e, block, index)}
        onDragEnd={handleDragEnd}
        onDragOver={(e) => {
          handleDragOver(e);
          setDragOverIndex(index);
        }}
        onDragLeave={(e) => {
          handleDragLeave(e);
          setDragOverIndex(null);
        }}
        onDrop={(e) => handleDrop(e, index)}
        onTouchStart={(e) => handleTouchStart(e, index)}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
        onKeyDown={(e) => handleKeyDown(e, index)}
        onClick={() => setSelectedElement(block.id)}
        tabIndex={0}
        role="button"
        aria-label={`${block.type} block - click to edit in toolbar`}
      >
        {/* Selection Indicator */}
        {isSelected && (
          <div className="absolute -top-3 -right-3 bg-blue-600 text-white px-2 py-1 text-xs rounded-full font-medium shadow-lg">
            Selected • Edit in toolbar ↑
          </div>
        )}

        {/* Block Type Indicators */}
        {(isButton || isImage) && (
          <div className="absolute top-2 left-2 opacity-0 group-hover:opacity-100 transition-opacity px-2 py-1 text-xs rounded font-medium">
            {isButton && <span className="bg-blue-600 text-white px-2 py-1 rounded">Button Block</span>}
            {isImage && <span className="bg-green-600 text-white px-2 py-1 rounded">Image Block</span>}
          </div>
        )}

        {/* Editable Content */}
        <div
          contentEditable
          className="min-h-[40px] outline-none focus:ring-2 focus:ring-blue-500 focus:ring-opacity-50 rounded p-2"
          dangerouslySetInnerHTML={{ __html: block.content }}
          onBlur={(e) => updateBlockContent(index, e.target.innerHTML)}
          onFocus={() => setSelectedElement(block.id)}
          onClick={(e) => {
            e.stopPropagation();
            // If it's an image block with placeholder, trigger image upload
            if (isImage && block.content.includes('Click+to+Upload+Image')) {
              const fileInput = document.createElement('input');
              fileInput.type = 'file';
              fileInput.accept = 'image/*';
              fileInput.style.display = 'none';

              fileInput.onchange = function (event) {
                const file = event.target.files[0];
                if (file) {
                  const reader = new FileReader();
                  reader.onload = function (e) {
                    const newContent = `<img
                      src="${e.target.result}"
                      alt="${file.name.replace(/\.[^/.]+$/, "")}"
                      width="400"
                      height="300"
                      style="width:100%; height:auto; display:block; margin:0 auto;"
                    >`;
                    updateBlockContent(index, newContent);
                  };
                  reader.readAsDataURL(file);
                }
                document.body.removeChild(fileInput);
              };

              document.body.appendChild(fileInput);
              fileInput.click();
            }
          }}
          style={{ cursor: 'text' }}
        />

        {/* Drag Handle */}
        <div className="absolute -left-3 top-1/2 transform -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity bg-white rounded shadow-lg border p-1">
          <GripVertical size={16} className="text-gray-400 cursor-grab hover:text-gray-600" />
        </div>
      </div>
    );
  };

  // ==========================================
  // 📊 DELIVERABILITY PANEL COMPONENT
  // ==========================================

  /**
   * Deliverability analysis panel with fix buttons
   */
  const DeliverabilityPanel = () => (
    <div className="bg-white border rounded-lg p-4 mb-6">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-lg font-semibold flex items-center gap-2">
          <Shield size={20} className="text-blue-600" />
          Deliverability Score
        </h3>
        <button
          onClick={() => setShowDeliverabilityPanel(!showDeliverabilityPanel)}
          className="text-gray-500 hover:text-gray-700"
        >
          {showDeliverabilityPanel ? <ChevronDown size={16} /> : <Plus size={16} />}
        </button>
      </div>

      {showDeliverabilityPanel && (
        <>
          <div className="flex items-center gap-3 mb-4">
            <div className="flex-1 bg-gray-200 rounded-full h-3">
              <div
                className={`h-3 rounded-full transition-all duration-500 ${deliverabilityScore >= 80 ? 'bg-green-500' :
                    deliverabilityScore >= 60 ? 'bg-yellow-500' : 'bg-red-500'
                  }`}
                style={{ width: `${deliverabilityScore}%` }}
              />
            </div>
            <div className={`text-xl font-bold ${deliverabilityScore >= 80 ? 'text-green-600' :
                deliverabilityScore >= 60 ? 'text-yellow-600' : 'text-red-600'
              }`}>
              {deliverabilityScore}/100
            </div>
          </div>

          {/* Warnings */}
          {spamWarnings.length > 0 && (
            <div className="mb-3">
              <h4 className="font-medium text-red-600 mb-2 flex items-center gap-1">
                <AlertTriangle size={16} />
                Spam Warnings ({spamWarnings.length})
              </h4>
              <ul className="text-sm text-red-600 space-y-1">
                {spamWarnings.map((warning, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <span className="mt-1">•</span>
                    <span>{warning}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Compatibility Warnings */}
          {compatibilityWarnings.length > 0 && (
            <div className="mb-3">
              <div className="flex justify-between items-center mb-2">
                <h4 className="font-medium text-orange-600 flex items-center gap-1">
                  <Monitor size={16} />
                  Compatibility Issues ({compatibilityWarnings.length})
                </h4>

                {compatibilityWarnings.some(warning => warning.includes('images missing')) && (
                  <button
                    onClick={fixImageDimensions}
                    className="px-3 py-1 bg-orange-500 text-white rounded hover:bg-orange-600 text-xs flex items-center gap-1"
                    title="Auto-fix image dimension issues"
                  >
                    <Settings size={12} />
                    Fix Images
                  </button>
                )}
              </div>

              <ul className="text-sm text-orange-600 space-y-1">
                {compatibilityWarnings.map((warning, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <span className="mt-1">•</span>
                    <span>{warning}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Accessibility Warnings */}
          {accessibilityWarnings.length > 0 && (
            <div className="mb-3">
              <h4 className="font-medium text-blue-600 mb-2 flex items-center gap-1">
                <Users size={16} />
                Accessibility Issues ({accessibilityWarnings.length})
              </h4>
              <ul className="text-sm text-blue-600 space-y-1">
                {accessibilityWarnings.map((warning, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <span className="mt-1">•</span>
                    <span>{warning}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* All Good Message */}
          {spamWarnings.length === 0 && compatibilityWarnings.length === 0 && accessibilityWarnings.length === 0 && (
            <div className="text-green-600 flex items-center gap-2">
              <CheckCircle size={16} />
              <span className="text-sm">Great! No deliverability issues detected.</span>
            </div>
          )}
        </>
      )}
    </div>
  );

  // ==========================================
  // 🎨 MAIN RENDER
  // ==========================================

  return (
    <div className="w-full bg-white">
      {/* Deliverability Panel */}
      <DeliverabilityPanel />

      {/* Undo Control Panel */}
      {dragHistory.length > 0 && (
        <div className="mb-4 p-3 bg-blue-50 border border-blue-200 rounded-lg flex items-center justify-between">
          <span className="text-sm text-blue-800">
            {dragHistory.length} action(s) available for undo
          </span>
          <button
            onClick={handleUndo}
            className="px-3 py-1 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 flex items-center gap-1"
          >
            ↶ Undo (Ctrl+Z)
          </button>
        </div>
      )}

      {/* Edit Mode Toggle */}
      <div className="mb-6 border-b">
        <div className="flex space-x-4">
          <button
            onClick={() => setEditMode('visual')}
            className={`px-4 py-2 border-b-2 transition-colors ${editMode === 'visual' ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-600'}`}
          >
            <Edit3 size={16} className="inline mr-2" />
            Visual Editor
          </button>
          <button
            onClick={() => setEditMode('drag-drop')}
            className={`px-4 py-2 border-b-2 transition-colors ${editMode === 'drag-drop' ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-600'}`}
          >
            <MousePointer size={16} className="inline mr-2" />
            Drag & Drop
          </button>
          <button
            onClick={() => setEditMode('html')}
            className={`px-4 py-2 border-b-2 transition-colors ${editMode === 'html' ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-600'}`}
          >
            <Code size={16} className="inline mr-2" />
            HTML Editor
          </button>
          <button
            onClick={() => setShowPreview(!showPreview)}
            className={`px-4 py-2 border-b-2 transition-colors ${showPreview ? 'border-green-500 text-green-600' : 'border-transparent text-gray-600'}`}
          >
            <Eye size={16} className="inline mr-2" />
            Preview
          </button>
        </div>
      </div>

      {/* Main Editor Area */}
      <div className="grid grid-cols-12 gap-6">
        {/* Drag & Drop Sidebar */}
        {editMode === 'drag-drop' && (
          <div className="col-span-3 bg-gray-50 p-4 rounded-lg">
            <h3 className="text-lg font-semibold mb-4">Email Blocks</h3>
            <div className="space-y-2">
              {emailBlockTypes.map((blockType) => (
                <div
                  key={blockType.id}
                  draggable
                  onDragStart={(e) => handleDragStart(e, blockType)}
                  className={`flex items-center gap-3 p-3 bg-white rounded-lg border border-gray-200 hover:border-blue-400 cursor-move transition-all ${blockType.id === 'button' ? 'ring-2 ring-blue-200 bg-blue-50' : ''
                    } ${blockType.id === 'image' ? 'ring-2 ring-green-200 bg-green-50' : ''
                    }`}
                >
                  <blockType.icon size={20} className="text-gray-600" />
                  <span className="text-sm font-medium">{blockType.name}</span>
                  {blockType.id === 'button' && (
                    <span className="ml-auto text-xs bg-blue-600 text-white px-2 py-1 rounded">Enhanced</span>
                  )}
                  {blockType.id === 'image' && (
                    <span className="ml-auto text-xs bg-green-600 text-white px-2 py-1 rounded">Upload Ready</span>
                  )}
                </div>
              ))}
            </div>

            {/* Personalization Panel */}

          </div>
        )}

        {/* Editor Content */}
        <div className={`${editMode === 'drag-drop' ? 'col-span-9' : 'col-span-12'}`}>
          {!showPreview ? (
            <>
              {/* Visual Editor */}
              {editMode === 'visual' && (
                <div className="border rounded-lg">
                  {/* Toolbar */}
                  <div className="border-b p-3 bg-gray-50 flex flex-wrap gap-2">
                    <div className="flex items-center gap-1 border-r pr-3 mr-3">
                      <select
                        value={fontFamily}
                        onChange={(e) => {
                          setFontFamily(e.target.value);
                          formatText('fontName', e.target.value);
                        }}
                        className="px-2 py-1 border rounded text-sm"
                      >
                        <option value="Arial">Arial</option>
                        <option value="Georgia">Georgia</option>
                        <option value="Times New Roman">Times New Roman</option>
                        <option value="Helvetica">Helvetica</option>
                        <option value="Verdana">Verdana</option>
                      </select>
                      <select
                        value={fontSize}
                        onChange={(e) => {
                          setFontSize(e.target.value);
                          formatText('fontSize', e.target.value);
                        }}
                        className="px-2 py-1 border rounded text-sm w-16"
                      >
                        <option value="12">12px</option>
                        <option value="14">14px</option>
                        <option value="16">16px</option>
                        <option value="18">18px</option>
                        <option value="20">20px</option>
                        <option value="24">24px</option>
                      </select>
                    </div>

                    <button onClick={() => formatText('bold')} className="p-2 rounded hover:bg-gray-200">
                      <Bold size={16} />
                    </button>
                    <button onClick={() => formatText('italic')} className="p-2 rounded hover:bg-gray-200">
                      <Italic size={16} />
                    </button>
                    <button onClick={() => formatText('underline')} className="p-2 rounded hover:bg-gray-200">
                      <Underline size={16} />
                    </button>

                    <div className="border-r pr-3 mr-3"></div>

                    <button onClick={() => formatText('justifyLeft')} className="p-2 rounded hover:bg-gray-200">
                      <AlignLeft size={16} />
                    </button>
                    <button onClick={() => formatText('justifyCenter')} className="p-2 rounded hover:bg-gray-200">
                      <AlignCenter size={16} />
                    </button>
                    <button onClick={() => formatText('justifyRight')} className="p-2 rounded hover:bg-gray-200">
                      <AlignRight size={16} />
                    </button>

                    <div className="border-r pr-3 mr-3"></div>

                    <button onClick={() => formatText('insertUnorderedList')} className="p-2 rounded hover:bg-gray-200">
                      <List size={16} />
                    </button>
                    <button onClick={() => formatText('insertOrderedList')} className="p-2 rounded hover:bg-gray-200">
                      <ListOrdered size={16} />
                    </button>
                    <button onClick={insertLink} className="p-2 rounded hover:bg-gray-200">
                      <Link size={16} />
                    </button>
                    <button onClick={insertImage} className="p-2 rounded hover:bg-gray-200">
                      <Image size={16} />
                    </button>

                    <div className="border-r pr-3 mr-3"></div>

                    <div className="flex items-center gap-2">
                      <input
                        type="color"
                        value={textColor}
                        onChange={(e) => changeTextColor(e.target.value)}
                        className="w-8 h-8 border rounded cursor-pointer"
                        title="Text Color"
                      />
                      <input
                        type="color"
                        value={backgroundColor}
                        onChange={(e) => changeBackgroundColor(e.target.value)}
                        className="w-8 h-8 border rounded cursor-pointer"
                        title="Background Color"
                      />
                    </div>
                  </div>

                  {/* Personalization Quick Insert */}
                  <div className="border-b p-2 bg-blue-50 flex flex-wrap gap-2">
                    <span className="text-sm font-medium text-blue-800">Quick Insert:</span>
                    {personalizationTags.slice(0, 4).map((tag, i) => (
                      <button
                        key={i}
                        onClick={() => insertPersonalizationTag(tag.tag)}
                        className="px-2 py-1 text-xs bg-blue-200 hover:bg-blue-300 rounded transition-colors"
                        title={tag.description}
                      >
                        {tag.tag}
                      </button>
                    ))}
                  </div>

                  {/* Editor Content */}
                  <div
                    ref={editorRef}
                    contentEditable
                    className="min-h-[500px] p-4 outline-none"
                    style={{ fontFamily, fontSize: `${fontSize}px` }}
                    onInput={(e) => setContent(e.target.innerHTML)}
                    dangerouslySetInnerHTML={{ __html: content }}
                  />
                </div>
              )}

              {/* Enhanced Drag & Drop Editor */}
              {editMode === 'drag-drop' && (
                <div className="border rounded-lg">
                  <div className="border-b p-3 bg-gray-50">
                    <div className="flex justify-between items-center">
                      <div>
                        <h3 className="text-lg font-semibold">Email Canvas</h3>
                        <p className="text-sm text-gray-600">Drag blocks from the sidebar • Use keyboard arrows to move selected blocks • Ctrl+Z to undo</p>
                      </div>
                      <div className="flex gap-2 text-sm text-gray-600">
                        <span>Grid: {gridSize}px</span>
                        <span>•</span>
                        <span>Blocks: {emailBlocks.length}</span>
                        {selectedElement && (
                          <>
                            <span>•</span>
                            <span className="text-blue-600 font-medium">
                              {emailBlocks.find(b => b.id === selectedElement)?.type || 'Unknown'} Selected
                            </span>
                          </>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* TOOLBAR WITH SETTINGS FOR SELECTED BLOCKS */}
                  {selectedElement && (() => {
                    const selectedBlock = emailBlocks.find(block => block.id === selectedElement);
                    const selectedIndex = emailBlocks.findIndex(block => block.id === selectedElement);

                    return (
                      <div className="border-b bg-blue-50 p-4">
                        <div className="flex items-center justify-between mb-3">
                          <h4 className="font-semibold text-blue-800 flex items-center gap-2">
                            <Settings size={16} />
                            {selectedBlock?.type === 'button' ? 'Button Settings & Resizing' :
                              selectedBlock?.type === 'image' ? 'Image Settings & Resizing' :
                                `${selectedBlock?.type} Settings`}
                          </h4>
                          <button
                            onClick={() => setSelectedElement(null)}
                            className="text-gray-500 hover:text-gray-700 p-1 rounded"
                            title="Close Settings"
                          >
                            <X size={16} />
                          </button>
                        </div>

                        {/* Button Settings in Toolbar */}
                        {selectedBlock?.type === 'button' && (
                          <div className="bg-white p-4 rounded-lg border">
                            <ButtonSettings
                              block={selectedBlock}
                              index={selectedIndex}
                              updateBlockContent={updateBlockContent}
                            />
                          </div>
                        )}

                        {/* Image Settings in Toolbar */}
                        {selectedBlock?.type === 'image' && (
                          <div className="bg-white p-4 rounded-lg border">
                            <ImageSettings
                              block={selectedBlock}
                              index={selectedIndex}
                              updateBlockContent={updateBlockContent}
                            />
                          </div>
                        )}

                        {/* Text Settings in Toolbar */}
                        {selectedBlock?.type === 'text' && (
                          <div className="bg-white p-4 rounded-lg border">
                            <TextSettings
                              block={selectedBlock}
                              index={selectedIndex}
                              updateBlockContent={updateBlockContent}
                            />
                          </div>
                        )}

                        {/* Universal Block Controls */}
                        <div className="mt-3 flex gap-2">
                          <button
                            onClick={() => duplicateBlock(selectedIndex)}
                            className="px-3 py-1 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 flex items-center gap-1"
                          >
                            <Copy size={14} />
                            Duplicate
                          </button>
                          <button
                            onClick={() => {
                              moveBlock(selectedIndex, Math.max(0, selectedIndex - 1));
                            }}
                            className="px-3 py-1 bg-gray-600 text-white rounded text-sm hover:bg-gray-700 flex items-center gap-1"
                            disabled={selectedIndex === 0}
                          >
                            <Move size={14} />
                            Move Up
                          </button>
                          <button
                            onClick={() => {
                              moveBlock(selectedIndex, Math.min(emailBlocks.length - 1, selectedIndex + 1));
                            }}
                            className="px-3 py-1 bg-gray-600 text-white rounded text-sm hover:bg-gray-700 flex items-center gap-1"
                            disabled={selectedIndex === emailBlocks.length - 1}
                          >
                            <Move size={14} className="rotate-180" />
                            Move Down
                          </button>
                          <button
                            onClick={() => deleteBlock(selectedIndex)}
                            className="px-3 py-1 bg-red-600 text-white rounded text-sm hover:bg-red-700 flex items-center gap-1"
                          >
                            <Trash2 size={14} />
                            Delete
                          </button>
                        </div>
                      </div>
                    );
                  })()}

                  {/* Main Canvas Area */}
                  <div
                    className="min-h-[500px] p-4 bg-white relative"
                    style={{
                      backgroundImage: `radial-gradient(circle, #e5e7eb 1px, transparent 1px)`,
                      backgroundSize: `${gridSize}px ${gridSize}px`
                    }}
                    onDragOver={handleDragOver}
                    onDrop={(e) => handleDrop(e)}
                    onDragLeave={handleDragLeave}
                  >
                    {emailBlocks.length === 0 ? (
                      <div className="text-center text-gray-500 py-20 border-2 border-dashed border-gray-300 rounded-lg">
                        <MousePointer size={48} className="mx-auto mb-4 text-gray-400" />
                        <p className="text-lg">Drag blocks here to start building your email</p>
                        <p className="text-sm">Choose from text, images, buttons, and more from the sidebar</p>
                        <p className="text-xs text-gray-400 mt-2">✨ Enhanced drag & drop with toolbar settings</p>
                      </div>
                    ) : (
                      <div className="space-y-4">
                        {emailBlocks.map((block, index) => (
                          <BlockElement key={block.id} block={block} index={index} />
                        ))}

                        {/* Drop Zone */}
                        <div
                          className={`h-16 border-2 border-dashed rounded-lg flex items-center justify-center text-gray-500 text-sm transition-all ${dragOverIndex === emailBlocks.length ? 'border-green-500 bg-green-50' : 'border-gray-300 hover:border-blue-400'
                            }`}
                          onDragOver={(e) => {
                            handleDragOver(e);
                            setDragOverIndex(emailBlocks.length);
                          }}
                          onDrop={(e) => handleDrop(e)}
                          onDragLeave={(e) => {
                            handleDragLeave(e);
                            setDragOverIndex(null);
                          }}
                        >
                          <MousePointer size={16} className="mr-2" />
                          Drop new blocks here
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* HTML Editor */}
              {editMode === 'html' && (
                <div className="border rounded-lg">
                  <div className="border-b p-3 bg-gray-50 flex justify-between items-center">
                    <h3 className="text-lg font-semibold">HTML Editor</h3>
                    <div className="flex gap-2">
                      <button
                        onClick={() => {
                          const formatted = htmlContent
                            .replace(/></g, '>\n<')
                            .replace(/^\s+|\s+$/g, '');
                          setHtmlContent(formatted);
                        }}
                        className="px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700"
                      >
                        Format HTML
                      </button>
                      <button
                        onClick={() => {
                          if (editMode === 'drag-drop') {
                            const blocksHtml = emailBlocks.map(block => block.content).join('\n');
                            setHtmlContent(blocksHtml);
                          } else {
                            setHtmlContent(content);
                          }
                        }}
                        className="px-3 py-1 text-sm bg-gray-600 text-white rounded hover:bg-gray-700"
                      >
                        Sync from Visual
                      </button>
                    </div>
                  </div>

                  {/* Personalization Quick Insert for HTML Mode */}
                  <div className="border-b p-2 bg-blue-50 flex flex-wrap gap-2">
                    <span className="text-sm font-medium text-blue-800">Insert:</span>
                    {personalizationTags.map((tag, i) => (
                      <button
                        key={i}
                        onClick={() => insertPersonalizationTag(tag.tag)}
                        className="px-2 py-1 text-xs bg-blue-200 hover:bg-blue-300 rounded transition-colors"
                        title={tag.description}
                      >
                        {tag.tag}
                      </button>
                    ))}
                  </div>

                  <textarea
                    ref={htmlEditorRef}
                    value={htmlContent}
                    onChange={(e) => setHtmlContent(e.target.value)}
                    className="w-full min-h-[500px] p-4 font-mono text-sm outline-none resize-none"
                    placeholder="Enter your HTML code here..."
                  />
                  <div className="border-t p-3 bg-gray-50">
                    <button
                      onClick={() => {
                        if (editMode === 'drag-drop') {
                          const parser = new DOMParser();
                          const doc = parser.parseFromString(htmlContent, 'text/html');
                          const elements = Array.from(doc.body.children);
                          const newBlocks = elements.map((el, index) => ({
                            id: Date.now() + index,
                            type: 'custom',
                            content: el.outerHTML,
                            styles: {},
                            position: index
                          }));
                          setEmailBlocks(newBlocks);
                        } else {
                          setContent(htmlContent);
                        }
                      }}
                      className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700"
                    >
                      Apply HTML Changes
                    </button>
                  </div>
                </div>
              )}
            </>
          ) : (
            /* Enhanced Preview Mode */
            <div className="border rounded-lg">
              <div className="border-b p-3 bg-gray-50 flex justify-between items-center">
                <h3 className="text-lg font-semibold">Template Preview</h3>
                <div className="flex gap-2">
                  <button
                    onClick={() => setPreviewMode('desktop')}
                    className={`p-2 rounded flex items-center gap-1 ${previewMode === 'desktop' ? 'bg-blue-600 text-white' : 'hover:bg-gray-200'}`}
                    title="Desktop Preview"
                  >
                    <Monitor size={16} />
                    Desktop
                  </button>
                  <button
                    onClick={() => setPreviewMode('tablet')}
                    className={`p-2 rounded flex items-center gap-1 ${previewMode === 'tablet' ? 'bg-blue-600 text-white' : 'hover:bg-gray-200'}`}
                    title="Tablet Preview"
                  >
                    <Tablet size={16} />
                    Tablet
                  </button>
                  <button
                    onClick={() => setPreviewMode('mobile')}
                    className={`p-2 rounded flex items-center gap-1 ${previewMode === 'mobile' ? 'bg-blue-600 text-white' : 'hover:bg-gray-200'}`}
                    title="Mobile Preview"
                  >
                    <Smartphone size={16} />
                    Mobile
                  </button>
                </div>
              </div>
              <div className="p-4 bg-gray-100 flex justify-center">
                <div
                  className={`bg-white shadow-lg transition-all duration-300 ${previewMode === 'desktop' ? 'w-full max-w-4xl' :
                      previewMode === 'tablet' ? 'w-[768px]' : 'w-[375px]'
                    }`}
                  style={{
                    minHeight: '400px',
                    border: previewMode !== 'desktop' ? '2px solid #ccc' : 'none',
                    borderRadius: previewMode !== 'desktop' ? '8px' : '0'
                  }}
                >
                  <div
                    className="p-4"
                    dangerouslySetInnerHTML={{
                      __html: editMode === 'drag-drop'
                        ? emailBlocks.map(block => block.content).join('')
                        : editMode === 'html'
                          ? htmlContent
                          : content
                    }}
                  />
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Quick Actions */}
      <div className="mt-6 flex flex-wrap gap-3">
        <button
          onClick={exportHTML}
          className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 flex items-center gap-2"
        >
          <Download size={16} />
          Export HTML
        </button>
        <button
          onClick={() => {
            setContent('');
            setHtmlContent('');
            setEmailBlocks([]);
            setDragHistory([]);
            setSelectedElement(null);
          }}
          className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 flex items-center gap-2"
        >
          <X size={16} />
          Clear All
        </button>
        {dragHistory.length > 0 && (
          <button
            onClick={handleUndo}
            className="px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 flex items-center gap-2"
          >
            ↶ Undo ({dragHistory.length})
          </button>
        )}
      </div>
    </div>
  );
});

export default EmailEditor;
