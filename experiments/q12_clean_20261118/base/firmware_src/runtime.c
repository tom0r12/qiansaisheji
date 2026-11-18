#include <stddef.h>
/* Minimal freestanding runtime for compiler-generated structure copies. */
void *memcpy(void *destination, const void *source, size_t count)
{
    unsigned char *d = (unsigned char *)destination;
    const unsigned char *s = (const unsigned char *)source;
    size_t i;
    for (i=0;i<count;++i) d[i]=s[i];
    return destination;
}
void *memset(void *destination, int value, size_t count)
{
    unsigned char *d = (unsigned char *)destination;
    size_t i;
    for (i=0;i<count;++i) d[i]=(unsigned char)value;
    return destination;
}
