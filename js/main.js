// Custom cursor - Commented out as requested but kept for future reference
/*
const cursor = document.querySelector('.cursor');
const cursorFollower = document.querySelector('.cursor-follower');
const links = document.querySelectorAll('a');

document.addEventListener('mousemove', (e) => {
    cursor.style.left = e.clientX + 'px';
    cursor.style.top = e.clientY + 'px';

    setTimeout(() => {
        cursorFollower.style.left = e.clientX + 'px';
        cursorFollower.style.top = e.clientY + 'px';
    }, 100);
});

document.addEventListener('mousedown', () => {
    cursor.style.transform = 'translate(-50%, -50%) scale(0.7)';
    cursorFollower.style.transform = 'translate(-50%, -50%) scale(0.7)';
});

document.addEventListener('mouseup', () => {
    cursor.style.transform = 'translate(-50%, -50%) scale(1)';
    cursorFollower.style.transform = 'translate(-50%, -50%) scale(1)';
});

links.forEach(link => {
    link.addEventListener('mouseenter', () => {
        cursor.style.transform = 'translate(-50%, -50%) scale(1.5)';
        cursor.style.backgroundColor = 'transparent';
        cursor.style.border = '2px solid var(--secondary-color)';
        cursorFollower.style.opacity = '0.3';
    });

    link.addEventListener('mouseleave', () => {
        cursor.style.transform = 'translate(-50%, -50%) scale(1)';
        cursor.style.backgroundColor = 'var(--secondary-color)';
        cursor.style.border = 'none';
        cursorFollower.style.opacity = '0.5';
    });
});
*/

// Countdown timer - Commented out as requested but kept for future reference
/*
const countdownDate = new Date();
countdownDate.setDate(countdownDate.getDate() + 30); // 30 days from now

function updateCountdown() {
    const now = new Date().getTime();
    const distance = countdownDate - now;

    // Time calculations
    const days = Math.floor(distance / (1000 * 60 * 60 * 24));
    const hours = Math.floor((distance % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
    const minutes = Math.floor((distance % (1000 * 60 * 60)) / (1000 * 60));
    const seconds = Math.floor((distance % (1000 * 60)) / 1000);

    // Display results
    document.querySelector('.days').textContent = days < 10 ? `0${days}` : days;
    document.querySelector('.hours').textContent = hours < 10 ? `0${hours}` : hours;
    document.querySelector('.minutes').textContent = minutes < 10 ? `0${minutes}` : minutes;
    document.querySelector('.seconds').textContent = seconds < 10 ? `0${seconds}` : seconds;

    // If countdown is finished
    if (distance < 0) {
        clearInterval(countdownTimer);
        document.querySelector('.countdown').innerHTML = "<h3>Blog is now live!</h3>";
    }
}

// Update countdown every second
const countdownTimer = setInterval(updateCountdown, 1000);
updateCountdown(); // Initial call
*/

// Notification button
const notifyBtn = document.querySelector('.notify-btn');
if (notifyBtn) {
    notifyBtn.addEventListener('click', (e) => {
        e.preventDefault();

        // Create a success message with animation
        const successMessage = document.createElement('div');
        successMessage.className = 'success-message';
        successMessage.innerHTML = 'Thank you! You will be notified when the blog launches.';

        // Insert the message before the button
        notifyBtn.parentNode.insertBefore(successMessage, notifyBtn);

        // Animate the message
        setTimeout(() => {
            successMessage.classList.add('show');
        }, 10);

        // Update button
        notifyBtn.innerHTML = '<span>You will be notified!</span><i class="fas fa-check"></i>';
        notifyBtn.classList.add('disabled');
        notifyBtn.disabled = true;

        // Remove the message after 5 seconds
        setTimeout(() => {
            successMessage.classList.remove('show');
            setTimeout(() => {
                successMessage.remove();
            }, 500);
        }, 5000);
    });
}

// Smooth scrolling for anchor links
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function(e) {
        const targetId = this.getAttribute('href');
        if (targetId === '#') return;

        const targetElement = document.querySelector(targetId);
        if (targetElement) {
            e.preventDefault();
            const headerOffset = 60;
            const elementPosition = targetElement.getBoundingClientRect().top;
            const offsetPosition = elementPosition + window.pageYOffset - headerOffset;

            window.scrollTo({
                top: offsetPosition,
                behavior: 'smooth'
            });
        }
    });
});

// Simplified animate on scroll with straightforward animations
const animateOnScroll = () => {
    const elements = document.querySelectorAll('.animate-on-scroll:not(.animated)');

    elements.forEach((element, index) => {
        const elementPosition = element.getBoundingClientRect().top;
        const windowHeight = window.innerHeight;

        if (elementPosition < windowHeight - 50) {
            // Add a small delay based on the element's index for staggered effect
            setTimeout(() => {
                element.classList.add('animated');
            }, index * 100); // 100ms delay between each element
        }
    });
};

// Mobile menu toggle (if needed in the future)
/*
const menuToggle = document.querySelector('.menu-toggle');
const mobileMenu = document.querySelector('.mobile-menu');

if (menuToggle && mobileMenu) {
    menuToggle.addEventListener('click', () => {
        menuToggle.classList.toggle('active');
        mobileMenu.classList.toggle('active');
    });
}
*/

// Check if device is touch-enabled
const isTouchDevice = () => {
    return (('ontouchstart' in window) ||
        (navigator.maxTouchPoints > 0) ||
        (navigator.msMaxTouchPoints > 0));
};

// Add touch class to body if it's a touch device
if (isTouchDevice()) {
    document.body.classList.add('touch-device');
}

// Simplified scroll handler without parallax effects
const handleScroll = () => {
    // Only run the animation check
    animateOnScroll();
};

// Initialize
window.addEventListener('scroll', handleScroll);
window.addEventListener('resize', () => {
    animateOnScroll();
    setVhProperty();
});

document.addEventListener('DOMContentLoaded', () => {
    animateOnScroll();
    setVhProperty();

    // Add a loaded class to the body for initial animations
    setTimeout(() => {
        document.body.classList.add('loaded');
    }, 100);
});

// Fix for iOS vh units
const setVhProperty = () => {
    let vh = window.innerHeight * 0.01;
    document.documentElement.style.setProperty('--vh', `${vh}px`);
};

window.addEventListener('orientationchange', setVhProperty);

// Run initial scroll handler
handleScroll();