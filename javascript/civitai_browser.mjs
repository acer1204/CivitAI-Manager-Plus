/**
 * CivitAI Browser - ES Module for card interactions.
 * Event delegation on document — no need to find specific elements.
 */

function updateGradioTextbox(selector, value) {
    const el = document.querySelector(selector + ' textarea');
    if (el) {
        el.value = value;
        el.dispatchEvent(new Event('input', { bubbles: true }));
    }
}

// --- Model Card Click: Open model info popup ---
document.addEventListener('click', function(e) {
    const card = e.target.closest('.civ-card:not(.civ-installed-card)');
    if (!card) return;
    if (e.target.closest('.civ-card-checkbox')) return;

    const modelId   = card.dataset.modelId;
    const versionId = card.dataset.versionId;
    if (modelId) {
        // Encode version hint so popup can filter to the correct version.
        // Format: "modelId:versionId_randomSuffix"  or  "modelId_randomSuffix"
        const randomSuffix = '_' + Math.random().toString(36).substring(2, 8);
        const idKey = versionId ? `${modelId}:${versionId}` : modelId;
        updateGradioTextbox('#civ_model_select', idKey + randomSuffix);

        document.querySelectorAll('.civ-card.civ-selected').forEach(c => c.classList.remove('civ-selected'));
        card.classList.add('civ-selected');
    }
});

// --- Card Checkbox Click: Toggle selection via Gradio ---
document.addEventListener('click', function(e) {
    const checkbox = e.target.closest('.civ-card-checkbox');
    if (!checkbox) return;
    
    // Don't allow clicking checkbox on installed models
    const card = checkbox.closest('.civ-card');
    if (card && card.dataset.installed === 'true') {
        e.preventDefault();
        e.stopPropagation();
        return;
    }
    
    e.stopPropagation();

    // Use selection key (model_id:version_id or plain model_id)
    const selectionKey = checkbox.dataset.selectionKey || checkbox.dataset.modelId;
    if (selectionKey) {
        // Toggle visual state immediately
        checkbox.classList.toggle('checked');

        // Toggle parent card selected state
        const card = checkbox.closest('.civ-card');
        if (card) {
            card.classList.toggle('civ-card-selected');
        }

        // Trigger Gradio update for backend state
        updateGradioTextbox('#civ_card_checkbox', selectionKey);
    }
});

// --- Installed Model Card Click - Directly open Model Info ---
document.addEventListener('click', function(e) {
    const card = e.target.closest('.civ-installed-card');
    if (!card) return;

    const modelId = card.dataset.modelId;
    const modelName = card.dataset.modelName || card.dataset.filename;

    // Check if modelId is valid (not empty or undefined)
    if (modelId && modelId.trim() !== '') {
        // Has CivitAI ID - open model info popup directly
        const modelIdInput = document.querySelector('#civ_installed_model_id textarea');
        
        if (modelIdInput) {
            // Force change by adding random suffix to ensure Gradio detects the change
            const randomSuffix = '_' + Math.random().toString(36).substring(2, 8);
            const uniqueValue = modelId + randomSuffix;
            
            modelIdInput.value = uniqueValue;
            
            // Trigger events in sequence: input → change → blur
            const inputEvent = new Event('input', { bubbles: true });
            const changeEvent = new Event('change', { bubbles: true });
            const blurEvent = new Event('blur', { bubbles: true });
            
            modelIdInput.dispatchEvent(inputEvent);
            modelIdInput.dispatchEvent(changeEvent);
            modelIdInput.dispatchEvent(blurEvent);
            // No need for manual popup trigger - MutationObserver will handle it
        }
        
        // Visual feedback
        document.querySelectorAll('.civ-installed-card.civ-installed-selected').forEach(c => {
            c.classList.remove('civ-installed-selected');
        });
        card.classList.add('civ-installed-selected');
    } else if (modelName) {
        // No CivitAI ID - show message
        alert('This model does not have CivitAI metadata. It was not downloaded from CivitAI Browser.\n\nModel: ' + modelName);
    }
});

// --- Folder Tree Click ---
document.addEventListener('click', function(e) {
    const folderItem = e.target.closest('.civ-folder-item, .civ-folder-subitem');
    if (!folderItem) return;
    
    const folder = folderItem.dataset.folder || '';
    
    // Update visual selection
    document.querySelectorAll('.civ-folder-item, .civ-folder-subitem').forEach(el => {
        el.classList.remove('civ-folder-selected');
    });
    folderItem.classList.add('civ-folder-selected');
    
    // Trigger filter
    updateGradioTextbox('#civ_installed_filter_folder', folder);
});

// --- Save Local Checkbox in Model Info Popup ---
document.addEventListener('change', function(e) {
    const checkbox = e.target.closest('.civ-save-local-checkbox');
    if (!checkbox) return;

    const modelId = checkbox.dataset.modelId;
    if (!modelId) return;

    // Show saving/deleting indicator immediately
    const sourceSpan = checkbox.closest('.civ-header-actions')?.querySelector('.civ-data-source');
    const label = checkbox.closest('.civ-save-local-label');
    if (checkbox.checked) {
        if (sourceSpan) {
            sourceSpan.textContent = '⏳ Saving...';
            sourceSpan.className = 'civ-data-source civ-source-saving';
        }
        if (label) label.classList.add('civ-saving');
    } else {
        if (sourceSpan) {
            sourceSpan.textContent = '🌐 Online';
            sourceSpan.className = 'civ-data-source civ-source-online';
        }
    }

    // Trigger save/delete via Gradio
    const action = checkbox.checked ? 'save' : 'delete';
    const randomSuffix = Math.random().toString(36).substring(2, 8);
    updateGradioTextbox('#civ_save_model_info', modelId + ':' + action + ':' + randomSuffix);
});

// Monitor save result
let _lastSaveResult = '';
setInterval(function() {
    const resultEl = document.querySelector('#civ_save_model_info_result textarea');
    if (!resultEl || !resultEl.value || resultEl.value === _lastSaveResult) return;
    _lastSaveResult = resultEl.value;

    const sourceSpan = document.querySelector('.civitai-overlay .civ-data-source');
    const label = document.querySelector('.civitai-overlay .civ-save-local-label');
    if (label) label.classList.remove('civ-saving');

    if (resultEl.value.startsWith('ok:')) {
        if (sourceSpan) {
            sourceSpan.textContent = '📁 Local';
            sourceSpan.className = 'civ-data-source civ-source-local';
        }
    } else if (resultEl.value.startsWith('deleted:')) {
        if (sourceSpan) {
            sourceSpan.textContent = '🌐 Online';
            sourceSpan.className = 'civ-data-source civ-source-online';
        }
    } else if (resultEl.value.startsWith('error:')) {
        if (sourceSpan) {
            sourceSpan.textContent = '❌ Error';
            sourceSpan.className = 'civ-data-source civ-source-online';
        }
    }
}, 200);

// --- Model Info Popup Window ---
function showModelInfoPopup(html) {
    console.log('[DEBUG] showModelInfoPopup called with html length:', html ? html.length : 0);
    console.log('[DEBUG] HTML preview:', html ? html.substring(0, 200) : 'empty');
    
    // Close existing popup if any
    hideModelInfoPopup();
    
    if (!html || html.trim() === '') {
        console.error('[DEBUG] showModelInfoPopup: html is empty!');
        return;
    }
    
    // Create overlay
    const overlay = document.createElement('div');
    overlay.className = 'civitai-overlay';
    
    // Create content div separately to avoid innerHTML escaping issues
    const contentDiv = document.createElement('div');
    contentDiv.className = 'civitai-overlay-content';
    
    // Create close button
    const closeBtn = document.createElement('div');
    closeBtn.className = 'civitai-overlay-close';
    closeBtn.innerHTML = '&times;';
    closeBtn.onclick = function(e) {
        e.stopPropagation();
        hideModelInfoPopup();
        return false;
    };
    
    overlay.appendChild(closeBtn);
    overlay.appendChild(contentDiv);
    
    // Now set the HTML content
    contentDiv.innerHTML = html;
    
    console.log('[DEBUG] showModelInfoPopup: overlay created, contentDiv innerHTML length:', contentDiv.innerHTML.length);
    
    // Close on overlay click (not content click)
    overlay.addEventListener('click', function(e) {
        if (e.target === overlay) {
            hideModelInfoPopup();
        }
    });
    
    // Close on Escape key
    overlay.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            hideModelInfoPopup();
        }
    });
    
    document.body.appendChild(overlay);
    document.body.style.overflow = 'hidden';
    
    console.log('[DEBUG] showModelInfoPopup: overlay appended to body');
    
    // Bind Send to txt2img buttons
    bindSendToTxt2ImgButtons();
    
    // Bind Copy buttons
    bindCopyButtons();
    
    // Bind Tab switching buttons
    bindTabSwitching();
    
    console.log('[DEBUG] showModelInfoPopup: complete');
}

// Monitor model_info_html for changes using polling
let lastModelInfoHtml = '';
let popupTriggerCount = 0;

setInterval(function() {
    const modelInfoHtml = document.querySelector('#civ_model_info_html');
    if (modelInfoHtml) {
        const currentHtml = modelInfoHtml.innerHTML;

        // Check if HTML changed and contains data-auto-popup
        if (currentHtml !== lastModelInfoHtml && currentHtml.includes('data-auto-popup="true"')) {
            console.log('[DEBUG] Model info HTML changed');
            console.log('[DEBUG] HTML length:', currentHtml.length);

            // Find the actual model info content element (skip Gradio wrappers that have "hide" class)
            const modelInfoContent = modelInfoHtml.querySelector('.civ-model-info');

            if (modelInfoContent) {
                console.log('[DEBUG] HTML contains valid model info');

                // Remove the attribute to prevent re-triggering
                modelInfoContent.removeAttribute('data-auto-popup');

                // Capture content HTML now (outerHTML of .civ-model-info only, without Gradio wrappers)
                const contentHtml = modelInfoContent.outerHTML;

                // Update last HTML
                lastModelInfoHtml = modelInfoHtml.innerHTML;

                // Show popup with delay
                popupTriggerCount++;
                const currentTriggerCount = popupTriggerCount;

                setTimeout(() => {
                    console.log('[DEBUG] Showing popup #' + currentTriggerCount);
                    showModelInfoPopup(contentHtml);
                }, 100);
            } else {
                console.log('[DEBUG] .civ-model-info not found, HTML length:', currentHtml.length);
            }
        }
    }
}, 200);  // Check every 200ms

function hideModelInfoPopup() {
    const overlay = document.querySelector('.civitai-overlay');
    if (overlay) {
        // Reset tracking so the same model can trigger the popup again
        lastModelInfoHtml = '';

        // Reset the model ID input when closing the popup (without triggering Gradio events)
        const modelIdInput = document.querySelector('#civ_installed_model_id textarea');
        if (modelIdInput) {
            modelIdInput.value = '';
            // Don't dispatch event - we don't want to trigger gr.update()
        }

        document.body.removeChild(overlay);
        document.body.style.overflow = 'auto';
    }
}

function bindSendToTxt2ImgButtons() {
    document.querySelectorAll('.civ-send-txt2img-btn').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            const geninfo = this.dataset.geninfo;
            if (!geninfo) {
                alert('No generation info available for this image.');
                return;
            }
            // Decode HTML entities and send directly to txt2img
            let decoded = geninfo.replace(/&#10;/g, '\n').replace(/&quot;/g, '"');

            // Auto-inject <lora:filename:1> at END of positive prompt if not already present.
            // Placing the tag at the end avoids shifting CLIP token positions for other words,
            // which would change attention weights and produce different images.
            const loraName = (this.dataset.loraName || '').trim();
            if (loraName) {
                const loraTag = `<lora:${loraName}:1>`;
                const negIdx = decoded.indexOf('\nNegative prompt:');
                const positivePrompt = negIdx >= 0 ? decoded.slice(0, negIdx) : decoded.split('\n')[0];
                const rest = decoded.slice(positivePrompt.length);
                if (!positivePrompt.toLowerCase().includes(loraName.toLowerCase())) {
                    // Append to end of positive prompt
                    decoded = positivePrompt.trimEnd() + ', ' + loraTag + rest;
                } else {
                    // LoRA tag already exists mid-prompt — move it to the end to avoid token shift
                    const loraPattern = new RegExp(',?\\s*<lora:' + loraName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ':[\\d.]+>\\s*,?', 'i');
                    const cleanedPositive = positivePrompt.replace(loraPattern, ', ').replace(/,\s*,/g, ',').trimEnd();
                    decoded = cleanedPositive + ', ' + loraTag + rest;
                }
            }

            genInfo_to_txt2img(decoded);

            // Visual feedback
            const orig = this.textContent;
            this.textContent = '✅ Sent!';
            setTimeout(() => { this.textContent = orig; }, 1500);
        });
    });
}

function _copyTextToClipboard(text) {
    // Modern Clipboard API (requires HTTPS or localhost with permission)
    if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
        return navigator.clipboard.writeText(text);
    }
    // Fallback: execCommand (works on HTTP without special permissions)
    return new Promise((resolve, reject) => {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.cssText = 'position:fixed;top:0;left:0;width:2px;height:2px;opacity:0;pointer-events:none';
        document.body.appendChild(ta);
        try {
            ta.focus();
            ta.select();
            if (document.execCommand('copy')) {
                resolve();
            } else {
                reject(new Error('execCommand copy failed'));
            }
        } catch (err) {
            reject(err);
        } finally {
            document.body.removeChild(ta);
        }
    });
}

function bindCopyButtons() {
    document.querySelectorAll('.civ-copy-btn').forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            e.preventDefault();

            const copyText = this.dataset.copy;
            if (!copyText) return;

            // Decode HTML entities (browser may have already decoded, but handle both cases)
            const decodedText = copyText.replace(/&#10;/g, '\n').replace(/&quot;/g, '"');
            const targetBtn = this;

            try {
                _copyTextToClipboard(decodedText).then(() => {
                    const originalText = targetBtn.textContent;
                    targetBtn.textContent = '✅ Copied!';
                    setTimeout(() => { targetBtn.textContent = originalText; }, 1500);
                }).catch(err => {
                    console.error('Failed to copy:', err);
                    alert('複製失敗，請手動複製。\n' + decodedText);
                });
            } catch (err) {
                // navigator.clipboard threw synchronously (undefined / permission error)
                console.error('Copy error:', err);
                alert('複製失敗，請手動複製。\n' + decodedText);
            }
        });
    });
}

function bindTabSwitching() {
    // Use event delegation on the overlay
    const overlay = document.querySelector('.civitai-overlay');
    if (!overlay) return;
    
    // Initial check - log tab content
    const descTab = overlay.querySelector('#civ-tab-description');
    const imgTab = overlay.querySelector('#civ-tab-images');
    console.log('[DEBUG] Initial tabs - Description:', descTab, 'Images:', imgTab);
    if (descTab) console.log('[DEBUG] Description tab HTML length:', descTab.innerHTML.length);
    if (imgTab) console.log('[DEBUG] Images tab HTML length:', imgTab.innerHTML.length);
    
    overlay.addEventListener('click', function(e) {
        const tabBtn = e.target.closest('.civ-tab-btn');
        if (!tabBtn) return;
        
        const tabName = tabBtn.dataset.tabTarget;
        if (!tabName) return;
        
        console.log('[DEBUG] Tab button clicked:', tabName);
        
        // Update button states
        overlay.querySelectorAll('.civ-tab-btn').forEach(btn => {
            btn.classList.remove('civ-tab-btn-active');
        });
        tabBtn.classList.add('civ-tab-btn-active');
        
        // Hide all tabs within this overlay
        const allTabs = overlay.querySelectorAll('.civ-tab-content');
        console.log('[DEBUG] Found tabs:', allTabs.length);
        allTabs.forEach(tab => {
            console.log('[DEBUG] Hiding tab:', tab.id, 'display:', tab.style.display);
            tab.style.display = 'none';
        });
        
        // Show selected tab - search within overlay
        const selectedTab = overlay.querySelector('#civ-tab-' + tabName);
        console.log('[DEBUG] Selected tab:', selectedTab);
        if (selectedTab) {
            selectedTab.style.display = 'block';
            console.log('[DEBUG] Showing tab:', tabName);
            console.log('[DEBUG] Tab innerHTML length:', selectedTab.innerHTML.length);
            
            // Scroll to top
            const modalContent = overlay.querySelector('.civitai-overlay-content');
            if (modalContent) {
                modalContent.scrollTop = 0;
            }
        } else {
            console.error('[DEBUG] Tab not found:', 'civ-tab-' + tabName);
        }
    });
}

// --- Send to txt2img ---
function genInfo_to_txt2img(genInfo) {
    if (!genInfo || genInfo.trim() === '') return;

    const cleanInfo = genInfo.replace(/^\d{3}\./, '');

    // --- Parse geninfo into parts ---
    // Positive prompt: everything before "\nNegative prompt:"
    const negMarker = '\nNegative prompt:';
    const negIdx = cleanInfo.indexOf(negMarker);

    let positivePrompt, afterPositive;
    if (negIdx >= 0) {
        positivePrompt = cleanInfo.slice(0, negIdx);
        afterPositive  = cleanInfo.slice(negIdx + 1); // "Negative prompt: ..."
    } else {
        const nl = cleanInfo.indexOf('\n');
        positivePrompt = nl >= 0 ? cleanInfo.slice(0, nl) : cleanInfo;
        afterPositive  = nl >= 0 ? cleanInfo.slice(nl + 1) : '';
    }

    // Negative prompt and params line
    let negativePrompt = '';
    let paramsLine = '';
    if (afterPositive.startsWith('Negative prompt:')) {
        const nl2 = afterPositive.indexOf('\n');
        if (nl2 >= 0) {
            negativePrompt = afterPositive.slice('Negative prompt:'.length, nl2).trim();
            paramsLine     = afterPositive.slice(nl2 + 1).trim();
        } else {
            negativePrompt = afterPositive.slice('Negative prompt:'.length).trim();
        }
    } else {
        paramsLine = afterPositive.trim();
    }

    // --- Directly set positive prompt (preserves original spacing) ---
    const posEl = document.querySelector('#txt2img_prompt textarea');
    if (posEl) {
        posEl.value = positivePrompt;
        posEl.dispatchEvent(new Event('input', { bubbles: true }));
    }

    // --- Directly set negative prompt ---
    const negEl = document.querySelector('#txt2img_neg_prompt textarea');
    if (negEl) {
        negEl.value = negativePrompt;
        negEl.dispatchEvent(new Event('input', { bubbles: true }));
    }

    // --- Use paste button ONLY for parameters (steps, sampler, CFG…) ---
    // Reconstruct a minimal geninfo so paste can parse the params line.
    if (paramsLine && posEl) {
        const pasteButton = document.querySelector('#paste');
        if (pasteButton) {
            // Put the full geninfo back so paste can parse everything;
            // positive/negative prompts will be overwritten again by paste,
            // but that is acceptable for parameter extraction.
            posEl.value = cleanInfo;
            posEl.dispatchEvent(new Event('input', { bubbles: true }));
            pasteButton.dispatchEvent(new Event('click', { bubbles: true }));

            // Restore the original-formatted positive prompt after paste normalises it
            setTimeout(() => {
                if (posEl) {
                    posEl.value = positivePrompt;
                    posEl.dispatchEvent(new Event('input', { bubbles: true }));
                }
                if (negEl) {
                    negEl.value = negativePrompt;
                    negEl.dispatchEvent(new Event('input', { bubbles: true }));
                }
            }, 100);
        }
    }

    // --- Enable Hires. fix checkbox if geninfo contains Hires params ---
    if (/Hires upscal/i.test(paramsLine)) {
        setTimeout(() => {
            const hrWrapper = document.querySelector('#txt2img_enable_hr');
            if (!hrWrapper) return;
            const hrCheckbox = hrWrapper.querySelector('input[type=checkbox]');
            if (hrCheckbox && !hrCheckbox.checked) {
                hrCheckbox.click();
            }
        }, 200);
    }
}

// --- Downloads Tab Auto-Refresh ---
// Trigger hidden auto-refresh textbox every 2s when there are active downloads
setInterval(function() {
    // Check if there are active downloads anywhere in the page
    const hasActive = document.querySelector('.civ-dl-queued, .civ-dl-downloading');
    if (!hasActive) return;
    // Trigger auto-refresh via hidden textbox
    const el = document.querySelector('#civ_dl_auto_refresh textarea');
    if (el) {
        el.value = Date.now().toString();
        el.dispatchEvent(new Event('input', { bubbles: true }));
    }
}, 2000);

// Make functions globally available
window.showModelInfoPopup = showModelInfoPopup;
window.hideModelInfoPopup = hideModelInfoPopup;
window.genInfo_to_txt2img = genInfo_to_txt2img;
