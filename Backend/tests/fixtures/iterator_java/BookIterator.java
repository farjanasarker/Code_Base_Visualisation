interface Iterator {
    boolean hasNext();
    Object next();
}

class BookCollection {
    private Object[] books;

    public Iterator createIterator() {
        return new BookIterator(books);
    }
}

class BookIterator implements Iterator {
    private Object[] books;
    private int position = 0;

    public BookIterator(Object[] books) {
        this.books = books;
    }

    public boolean hasNext() {
        return position < books.length;
    }

    public Object next() {
        return books[position];
    }
}
