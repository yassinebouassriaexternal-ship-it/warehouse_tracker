// Glassmorphism Effects and Animations for Warehouse Tracker

document.addEventListener('DOMContentLoaded', function() {
    // Initialize glassmorphism effects
    initGlassmorphism();
    
    // Initialize smooth page transitions
    initPageTransitions();
    
    // Initialize interactive effects
    initInteractiveEffects();
    
    // Initialize loading animations
    initLoadingAnimations();
});

function initGlassmorphism() {
    // Add glass effect to all cards
    const cards = document.querySelectorAll('.card');
    cards.forEach(card => {
        if (!card.classList.contains('glass-container')) {
            card.classList.add('glass-container');
        }
    });
    
    // Add glass effect to buttons that don't have glass classes
    const buttons = document.querySelectorAll('.btn:not([class*="glass"])');
    buttons.forEach(btn => {
        // Determine button type and add appropriate glass class
        if (btn.classList.contains('btn-primary')) {
            btn.classList.add('btn-primary-glass');
        } else if (btn.classList.contains('btn-success')) {
            btn.classList.add('btn-success-glass');
        } else if (btn.classList.contains('btn-warning')) {
            btn.classList.add('btn-warning-glass');
        } else if (btn.classList.contains('btn-danger')) {
            btn.classList.add('btn-danger-glass');
        } else if (btn.classList.contains('btn-info')) {
            btn.classList.add('btn-info-glass');
        } else {
            btn.classList.add('btn-glass');
        }
    });
    
    // Add glass effect to form controls (but not filter inputs)
    const formControls = document.querySelectorAll('.form-control:not(.form-control-glass):not(.filter-input)');
    formControls.forEach(control => {
        control.classList.add('form-control-glass');
    });
    
    // Add glass effect to tables
    const tables = document.querySelectorAll('.table:not(.table-glass)');
    tables.forEach(table => {
        table.classList.add('table-glass');
    });
    
    // Add glass effect to progress bars
    const progressBars = document.querySelectorAll('.progress-bar:not(.progress-bar-glass)');
    progressBars.forEach(bar => {
        bar.classList.add('progress-bar-glass');
    });
    
    const progress = document.querySelectorAll('.progress:not(.progress-glass)');
    progress.forEach(prog => {
        prog.classList.add('progress-glass');
    });
}

function initPageTransitions() {
    // Add page enter animation to main content
    const container = document.querySelector('.container');
    if (container) {
        container.classList.add('page-enter');
        
        // Trigger animation after a short delay
        setTimeout(() => {
            container.classList.add('page-enter-active');
            container.classList.remove('page-enter');
        }, 100);
    }
    
    // Add staggered animation to cards
    const cards = document.querySelectorAll('.card');
    cards.forEach((card, index) => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(30px)';
        
        setTimeout(() => {
            card.style.transition = 'all 0.6s cubic-bezier(0.4, 0, 0.2, 1)';
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        }, 150 + (index * 100));
    });
}

function initInteractiveEffects() {
    // Add ripple effect to glass buttons
    const glassButtons = document.querySelectorAll('[class*="btn-"][class*="glass"]');
    glassButtons.forEach(button => {
        button.addEventListener('click', createRipple);
    });
    
    // Metric card hover effects now handled by CSS for consistency
    
    // Tilt effects removed for better usability
}

function createRipple(event) {
    const button = event.currentTarget;
    const ripple = document.createElement('span');
    const rect = button.getBoundingClientRect();
    const size = Math.max(rect.width, rect.height);
    const x = event.clientX - rect.left - size / 2;
    const y = event.clientY - rect.top - size / 2;
    
    ripple.style.cssText = `
        position: absolute;
        border-radius: 50%;
        background: rgba(255, 255, 255, 0.3);
        transform: scale(0);
        animation: ripple 0.6s linear;
        width: ${size}px;
        height: ${size}px;
        left: ${x}px;
        top: ${y}px;
    `;
    
    button.style.position = 'relative';
    button.style.overflow = 'hidden';
    button.appendChild(ripple);
    
    setTimeout(() => {
        ripple.remove();
    }, 600);
}

// Tilt functions removed for better usability

function initLoadingAnimations() {
    // Add loading animation to data tables
    const tables = document.querySelectorAll('table[id*="Table"]');
    tables.forEach(table => {
        // Show loading animation while DataTable initializes
        if ($.fn.DataTable && $.fn.DataTable.isDataTable(table)) {
            const wrapper = table.closest('.dataTables_wrapper');
            if (wrapper) {
                wrapper.style.opacity = '0';
                wrapper.style.transform = 'translateY(20px)';
                
                setTimeout(() => {
                    wrapper.style.transition = 'all 0.5s ease';
                    wrapper.style.opacity = '1';
                    wrapper.style.transform = 'translateY(0)';
                }, 300);
            }
        }
    });
}

// Add CSS for ripple animation
const style = document.createElement('style');
style.textContent = `
    @keyframes ripple {
        to {
            transform: scale(4);
            opacity: 0;
        }
    }
    
    .glass-hover-effect {
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    }
    
    .glass-hover-effect:hover {
        transform: translateY(-2px);
        box-shadow: 0 12px 40px 0 rgba(31, 38, 135, 0.5);
    }
`;
document.head.appendChild(style);

// Utility function to add glass loading spinner
function showGlassLoading(element) {
    const loader = document.createElement('div');
    loader.className = 'glass-loading';
    loader.style.margin = '20px auto';
    loader.style.display = 'block';
    
    const container = document.createElement('div');
    container.style.textAlign = 'center';
    container.appendChild(loader);
    
    element.appendChild(container);
    return container;
}

function hideGlassLoading(loaderContainer) {
    if (loaderContainer && loaderContainer.parentNode) {
        loaderContainer.parentNode.removeChild(loaderContainer);
    }
}

// Export functions for use in other scripts
window.glassmorphismUtils = {
    showGlassLoading,
    hideGlassLoading,
    createRipple,
    initGlassmorphism
}; 