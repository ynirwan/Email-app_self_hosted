FROM node:20-alpine

WORKDIR /app

# Set environment variables
ENV PATH /app/node_modules/.bin:$PATH

# Copy configuration files first
COPY package*.json ./
COPY vite.config.js ./
COPY tailwind.config.js ./
COPY postcss.config.js ./

# Install dependencies as root
RUN npm cache clean --force && \
    npm install

# Copy project files
COPY . .

# Create non-root user and set proper permissions
RUN addgroup -g 1001 -S nodejs && \
    adduser -S reactjs -u 1001 && \
    chown -R reactjs:nodejs /app && \
    chmod -R 755 /app

# Switch to non-root user AFTER setting permissions
#USER reactjs

EXPOSE 5173

CMD ["npm", "run", "dev"]

