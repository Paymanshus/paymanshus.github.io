# Next.js Portfolio Starter

This is a starter template for creating a portfolio site with Next.js, including a blog section.

## Getting Started

1. Install Node.js (if not already installed): [https://nodejs.org/](https://nodejs.org/)

2. Create a new Next.js project:
   ```bash
   npx create-next-app@latest my-portfolio
   cd my-portfolio
   ```

3. When prompted, select the following options:
   - Would you like to use TypeScript? Yes
   - Would you like to use ESLint? Yes
   - Would you like to use Tailwind CSS? Yes
   - Would you like to use `src/` directory? Yes
   - Would you like to use App Router? Yes
   - Would you like to customize the default import alias? No

4. Start the development server:
   ```bash
   npm run dev
   ```

5. Open [http://localhost:3000](http://localhost:3000) in your browser to see the result.

## Project Structure

```
my-portfolio/
├── public/            # Static files (images, etc.)
├── src/
│   ├── app/           # App Router pages
│   │   ├── page.tsx   # Home page
│   │   ├── layout.tsx # Root layout
│   │   ├── blog/      # Blog section
│   │   │   └── page.tsx
│   │   │   └── [slug]/
│   │   │       └── page.tsx
│   │   │
│   │   ├── components/    # Reusable components
│   │   ├── lib/           # Utility functions
│   │   └── styles/        # Global styles
│   │
│   ├── posts/             # Markdown blog posts
│   └── next.config.js     # Next.js configuration
│
└── package.json       # Project dependencies
```

## Adding Blog Functionality

1. Install required packages:
   ```bash
   npm install gray-matter remark remark-html
   ```

2. Create a `posts` directory in the root of your project to store your blog posts as Markdown files.

3. Create utility functions to parse and render Markdown files.

4. Create blog pages to list and display individual posts.

## Deploying to GitHub Pages

1. Install the `gh-pages` package:
   ```bash
   npm install --save-dev gh-pages
   ```

2. Add the following scripts to your `package.json`:
   ```json
   "scripts": {
     "build": "next build",
     "export": "next export",
     "deploy": "next build && next export && touch out/.nojekyll && gh-pages -d out -t true"
   }
   ```

3. Create a `.github/workflows/deploy.yml` file for GitHub Actions to automate deployment.

## Resources

- [Next.js Documentation](https://nextjs.org/docs)
- [Learn Next.js](https://nextjs.org/learn)
- [Tailwind CSS Documentation](https://tailwindcss.com/docs)
- [GitHub Pages Deployment](https://github.com/vercel/next.js/tree/canary/examples/github-pages) 