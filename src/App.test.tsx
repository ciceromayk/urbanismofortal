import { render, screen } from '@testing-library/react';
import App from './App';

describe('App', () => {
  it('renderiza o título principal', () => {
    render(<App />);
    expect(screen.getByRole('heading', { name: /urbanismo de fortaleza/i })).toBeInTheDocument();
  });
});
