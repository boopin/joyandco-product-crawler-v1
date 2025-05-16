def generate_tracking_snippets():
    """Generate HTML file with tracking code snippets for Google and Meta"""
    
    # Google Tag for remarketing and conversion tracking
    google_tag = """
    <!-- Google tag (gtag.js) -->
    <script async src="https://www.googletagmanager.com/gtag/js?id=YOUR-ID"></script>
    <script>
      window.dataLayer = window.dataLayer || [];
      function gtag(){dataLayer.push(arguments);}
      gtag('js', new Date());
    
      gtag('config', 'YOUR-ID');
      
      // Dynamic remarketing event code
      gtag('event', 'view_item', {
        'send_to': 'YOUR-ID',
        'value': document.querySelector('.product-price')?.innerText.replace(/[^0-9.]/g, ''),
        'items': [{
          'id': window.location.pathname.split('/').pop(),
          'google_business_vertical': 'retail'
        }]
      });
    </script>
    """
    
    # Meta Pixel code
    meta_pixel = """
    <!-- Meta Pixel Code -->
    <script>
    !function(f,b,e,v,n,t,s)
    {if(f.fbq)return;n=f.fbq=function(){n.callMethod?
    n.callMethod.apply(n,arguments):n.queue.push(arguments)};
    if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';
    n.queue=[];t=b.createElement(e);t.async=!0;
    t.src=v;s=b.getElementsByTagName(e)[0];
    s.parentNode.insertBefore(t,s)}(window, document,'script',
    'https://connect.facebook.net/en_US/fbevents.js');
    fbq('init', 'YOUR-PIXEL-ID');
    fbq('track', 'PageView');
    
    // Add Meta product microdata for product pages
    if (window.location.pathname.includes('/product/')) {
      fbq('track', 'ViewContent', {
        content_name: document.querySelector('.product-title')?.innerText,
        content_ids: [window.location.pathname.split('/').pop()],
        content_type: 'product',
        value: document.querySelector('.product-price')?.innerText.replace(/[^0-9.]/g, ''),
        currency: 'AED'
      });
    }
    </script>
    <!-- End Meta Pixel Code -->
    """
    
    # Write to an HTML file
    with open('tracking_snippets.html', 'w') as f:
        f.write("<h1>Google Tag Snippet</h1>\n")
        f.write("<p>Add this to the &lt;head&gt; section of your website:</p>\n")
        f.write("<pre>" + google_tag + "</pre>\n\n")
        f.write("<h1>Meta Pixel Snippet</h1>\n")
        f.write("<p>Add this to the &lt;head&gt; section of your website:</p>\n")
        f.write("<pre>" + meta_pixel + "</pre>\n")

if __name__ == "__main__":
    generate_tracking_snippets()
