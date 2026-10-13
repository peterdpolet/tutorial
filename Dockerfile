# The image: nginx with a COPY of ./site baked into it at build time.
# Once built, the image is a sealed snapshot. Editing ./site later does NOT change it.
FROM nginx:alpine
COPY site/ /usr/share/nginx/html/
