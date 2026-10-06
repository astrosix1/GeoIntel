import Shell from './shell/Shell';
import { useShareLink } from './state/useShareLink';

function App() {
  useShareLink();
  return <Shell />;
}

export default App;
